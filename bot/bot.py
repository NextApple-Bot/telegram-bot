from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from bot.config import config

# === Главный роутер (в нём уже подключены все остальные) ===
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

    # Подключаем только главный роутер
    dp.include_router(main_router)

    logger.info("Главный роутер + ErrorHandlerMiddleware подключены")
    return dp


async def main() -> None:
    bot = create_bot()
    dp = create_dispatcher()

    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Запуск бота в режиме polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
