# -*- coding: utf-8 -*-
"""sprinthealth_bron_bot — kirish nuqtasi.

Ishga tushirish:
    venv\\Scripts\\activate      (Windows)
    source venv/bin/activate    (Linux)
    python -m db.migrate        # baza sxemasini qo'llash
    python main.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats,
)

from config import ConfigError, load_settings, setup_logging
from db.pool import close_pool, init_pool
from handlers import admin, bron, common, groups, pharmacy_admin, stats
from middlewares.auth import AuthMiddleware
from middlewares.context import CompanyMiddleware
from services import company as company_service
from web import server as web_server

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Botni qayta ishga tushirish"),
    BotCommand(command="help", description="Yordam va qo'llanma"),
    BotCommand(command="id", description="ID raqamimni ko'rsatish"),
    BotCommand(command="admin", description="Admin panel (faqat adminlar)"),
]


def build_dispatcher(settings) -> Dispatcher:
    # workflow_data — handlerlar `settings` argumentini so'rasa shu keladi
    dp = Dispatcher(settings=settings)

    # Outer middleware: filtrlar chaqirilishidan oldin ishlaydi, shuning
    # uchun `is_admin` router filtrlariga ham yetib boradi.
    auth = AuthMiddleware(bootstrap_admin_id=settings.bootstrap_admin_id)
    company_mw = CompanyMiddleware(company_code=settings.company_code)
    for observer in (dp.message, dp.callback_query, dp.inline_query):
        observer.outer_middleware(auth)
        observer.outer_middleware(company_mw)

    # Bron va admin oqimlari faqat shaxsiy chatda. Guruhlarda bot
    # xabarlarga umuman javob bermaydi — u yerda faqat bron xabari va
    # to'lov tugmasi bo'lishi kerak.
    # Diqqat: bu faqat message'ga qo'yiladi. callback_query (to'lov
    # tugmasi) va inline_query (guruhdan apteka qidirish) tegilmaydi.
    private_only = F.chat.type == "private"
    for router in (admin.router, stats.router, pharmacy_admin.router, bron.router):
        router.message.filter(private_only)

    # Tartib muhim: admin routerlari oldinroq (ular IsAdmin bilan
    # cheklangan, o'tmasa keyingisiga tushadi). groups eng oldinda —
    # guruh tugmasi admin bo'lmagan buxgalterga ham ishlashi kerak.
    dp.include_router(groups.router)
    dp.include_router(admin.router)
    dp.include_router(stats.router)
    dp.include_router(pharmacy_admin.router)
    dp.include_router(bron.router)
    dp.include_router(common.router)
    return dp


async def setup_commands(bot: Bot) -> None:
    """Buyruqlar menyusi faqat shaxsiy chatda ko'rinadi.

    Guruhlarda «/» menyusi umuman chiqmasligi kerak — u yerda bot bilan
    muloqot qilinmaydi, faqat bron xabari va to'lov tugmasi bo'ladi.
    Bo'sh ro'yxat aynan shuni beradi: Telegram bo'sh ro'yxatni "buyruq
    yo'q" deb tushunadi va umumiyroq scope'ga qaytmaydi.
    """
    await bot.delete_my_commands()  # eski umumiy ro'yxatni olib tashlaymiz
    await bot.set_my_commands(COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())


async def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as e:
        logging.basicConfig(level=logging.INFO)
        logger.error("❌ Sozlama xatosi: %s", e)
        raise SystemExit(1)

    setup_logging(settings.log_level)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(settings)

    await init_pool(settings)
    company = await company_service.get(settings.company_code)
    logger.info(
        "Kompaniya: %s (sho't kodi %s)", company["name"], company["account_code"]
    )

    await setup_commands(bot)
    web_runner = await web_server.start(settings)
    me = await bot.get_me()
    logger.info("Bot ishga tushdi... 🚀  @%s", me.username)

    try:
        await dp.start_polling(bot)
    finally:
        if web_runner:
            await web_runner.cleanup()
        await close_pool()
        await bot.session.close()
        logger.info("Bot to'xtatildi.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
