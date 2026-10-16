# -*- coding: utf-8 -*-
"""Sozlamalar — env faqat shu yerda o'qiladi.

farm_botda ADMINS ikki faylda alohida o'qilardi va sinxrondan chiqib ketardi.
Bu yerda env bitta joyda, adminlar esa umuman env'da emas — bazada
(app_user.role='admin'). Env'dagi BOOTSTRAP_ADMIN_ID faqat birinchi
adminni yaratish uchun: baza bo'sh bo'lsa, o'sha ID admin qilib qo'yiladi.
"""
import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class ConfigError(RuntimeError):
    """Sozlama noto'g'ri yoki yetishmayapti."""


def _req(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise ConfigError(f".env da {key} ko'rsatilmagan")
    return val


def _req_int(key: str) -> int:
    raw = _req(key)
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f".env da {key} butun son bo'lishi kerak, hozir: {raw!r}")


def _opt_int(key: str) -> int | None:
    raw = os.getenv(key, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f".env da {key} butun son bo'lishi kerak, hozir: {raw!r}")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    bron_group_id: int
    oplata_group_id: int
    bootstrap_admin_id: int | None

    db_user: str
    db_password: str
    db_name: str
    db_host: str
    db_port: int

    log_level: str
    company_code: str

    # Markirovka sahifasi (web). web_port bo'sh bo'lsa web o'chiq.
    web_port: int | None = None
    web_token: str = ""

    @property
    def db_config(self) -> dict:
        return {
            "user": self.db_user,
            "password": self.db_password,
            "database": self.db_name,
            "host": self.db_host,
            "port": self.db_port,
        }

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


def load_settings() -> Settings:
    return Settings(
        bot_token=_req("BOT_TOKEN"),
        bron_group_id=_req_int("BRON_GROUP_ID"),
        oplata_group_id=_req_int("OPLATA_GROUP_ID"),
        bootstrap_admin_id=_opt_int("BOOTSTRAP_ADMIN_ID"),
        db_user=_req("DB_USER"),
        db_password=_req("DB_PASSWORD"),
        db_name=_req("DB_NAME"),
        db_host=os.getenv("DB_HOST", "localhost").strip() or "localhost",
        db_port=int(os.getenv("DB_PORT", "5432").strip() or "5432"),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        company_code=os.getenv("COMPANY_CODE", "sprinthealth").strip() or "sprinthealth",
        web_port=_opt_int("WEB_PORT"),
        web_token=_web_token(),
    )


def _web_token() -> str:
    """WEB_PORT berilgan bo'lsa token majburiy — sahifa ochiq IP'da turadi."""
    token = os.getenv("WEB_TOKEN", "").strip()
    if os.getenv("WEB_PORT", "").strip() and len(token) < 16:
        raise ConfigError("WEB_PORT berilgan — WEB_TOKEN kamida 16 belgi bo'lishi kerak")
    return token


def load_db_settings() -> Settings:
    """Migration uchun: bot tokeni va guruhlar hali bo'lmasa ham ishlaydi."""
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", ""),
        bron_group_id=_opt_int("BRON_GROUP_ID") or 0,
        oplata_group_id=_opt_int("OPLATA_GROUP_ID") or 0,
        bootstrap_admin_id=_opt_int("BOOTSTRAP_ADMIN_ID"),
        db_user=_req("DB_USER"),
        db_password=_req("DB_PASSWORD"),
        db_name=_req("DB_NAME"),
        db_host=os.getenv("DB_HOST", "localhost").strip() or "localhost",
        db_port=int(os.getenv("DB_PORT", "5432").strip() or "5432"),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        company_code=os.getenv("COMPANY_CODE", "sprinthealth").strip() or "sprinthealth",
    )


def setup_logging(level: str = "INFO") -> None:
    import logging

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # aiogram har update uchun INFO yozadi — log'ni ko'mib tashlaydi
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
