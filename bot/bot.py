from __future__ import annotations

import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from bot.config import config

# === Главный роутер ===
from bot.handlers import router as main_router

# === Middleware ===
from bot.middleware.error_handler import ErrorHandlerMiddleware


def create_bot() -> Bot:
    return Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ErrorHandlerMiddleware())
    dp.include_router(main_router)
    logger.info("Главный роутер + ErrorHandlerMiddleware подключены")
    return dp


async def main_webhook():
    """Запуск через webhook (на Render)"""
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    bot = create_bot()
    dp = create_dispatcher()

    await bot.delete_webhook(drop_pending_updates=True)

    webhook_url = f"{config.RENDER_EXTERNAL_URL}/webhook"
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info(f"Webhook установлен: {webhook_url}")

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    await site.start()

    logger.info("Бот запущен в режиме Webhook")
    await asyncio.Event().wait()


async def main_polling():
    """Запуск через polling (локально)"""
    bot = create_bot()
    dp = create_dispatcher()

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен в режиме Polling (локально)")

    await dp.start_polling(bot)


if __name__ == "__main__":
    if os.getenv("RENDER_EXTERNAL_URL"):
        # Запуск на Render
        asyncio.run(main_webhook())
    else:
        # Локальный запуск
        asyncio.run(main_polling())
