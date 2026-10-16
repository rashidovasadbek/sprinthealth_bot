# -*- coding: utf-8 -*-
"""Markirovka sahifasi — oplataga hali yuborilmagan bronlar.

Bot bilan bitta jarayonda ishlaydi (aiohttp aiogram bilan birga keladi,
yangi kutubxona kerak emas). Faqat O'QIYDI — bazaga hech narsa yozmaydi.

    GET /markirovka          — HTML sahifa
    GET /api/pending         — JSON (X-Token sarlavhasi yoki ?token=)

CORS ochiq: sahifa kompyuterdan (file://) ochilsa ham API'ni chaqira oladi.
Himoya — faqat WEB_TOKEN.
"""
import hmac
import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from aiohttp import web

from db import repo
from services import company as company_service

logger = logging.getLogger(__name__)

PAGE = Path(__file__).with_name("markirovka.html")
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "X-Token",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
}


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(type(o))


def _token_ok(request: web.Request) -> bool:
    expected = request.app["token"]
    got = request.headers.get("X-Token") or request.query.get("token", "")
    return bool(expected) and hmac.compare_digest(got.encode(), expected.encode())


async def page(request: web.Request) -> web.Response:
    return web.Response(
        text=PAGE.read_text(encoding="utf-8"),
        content_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


async def pending(request: web.Request) -> web.Response:
    if request.method == "OPTIONS":
        return web.Response(headers=CORS)
    if not _token_ok(request):
        return web.json_response({"error": "token noto'g'ri"}, status=401, headers=CORS)

    company = await company_service.get(request.app["company_code"])
    rows = await repo.list_pending_brons(company["id"])
    brons = []
    for r in rows:
        d = dict(r)
        d["items"] = json.loads(d["items"]) if isinstance(d["items"], str) else d["items"]
        brons.append(d)

    body = json.dumps(
        {"company": company["name"], "generated_at": datetime.now().astimezone(),
         "brons": brons},
        default=_default, ensure_ascii=False,
    )
    return web.Response(
        text=body, content_type="application/json",
        headers={**CORS, "Cache-Control": "no-store"},
    )


def build_app(settings) -> web.Application:
    app = web.Application()
    app["token"] = settings.web_token
    app["company_code"] = settings.company_code
    app.router.add_get("/markirovka", page)
    app.router.add_route("GET", "/api/pending", pending)
    app.router.add_route("OPTIONS", "/api/pending", pending)
    return app


async def start(settings) -> web.AppRunner | None:
    """WEB_PORT berilmagan bo'lsa hech narsa qilmaydi."""
    if not settings.web_port:
        return None
    runner = web.AppRunner(build_app(settings), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", settings.web_port).start()
    logger.info("Markirovka sahifasi: http://0.0.0.0:%s/markirovka", settings.web_port)
    return runner
