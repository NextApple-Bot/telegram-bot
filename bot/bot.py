from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from bot.config import config

# === Routers ===
from bot.handlers.commands import router as commands_router
from bot.handlers.callbacks import router as callbacks_router
from bot.handlers import router as topics_router

from bot.handlers.seller.router import router as seller_router
from bot.handlers.admin.router import router as admin_router
from bot.handlers.common.router import router as common_router

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

    dp.include_router(topics_router)
    dp.include_router(commands_router)
    dp.include_router(callbacks_router)
    dp.include_router(seller_router)
    dp.include_router(admin_router)
    dp.include_router(common_router)   # new common module

    logger.info("All routers + ErrorHandlerMiddleware included successfully")
    return dp


async def main() -> None:
    bot = create_bot()
    dp = create_dispatcher()

    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Starting bot in polling mode...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
