import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from bot.config import config as bot_config   # ← теперь работает
from bot.db.session import async_session, init_db
from bot.middleware import setup_middleware
from bot.handlers import setup_handlers
from bot.background import start_background_tasks
from web_admin.app import admin_app
from utils.logger import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager для FastAPI + aiogram"""
    # При старте
    await init_db()
    setup_logging()
    
    logger = logging.getLogger(__name__)
    logger.info("🚀 Запускаем Telegram Bot...")

    # Инициализация бота
    session = AiohttpSession()
    bot = Bot(token=bot_config.BOT_TOKEN, session=session)
    
    # Настройка middleware и handlers
    setup_middleware(bot)
    setup_handlers(bot)

    # Запуск background задач
    await start_background_tasks(bot)

    yield

    # При выключении
    await bot.session.close()
    logger.info("🛑 Бот остановлен.")


# Создаём FastAPI приложение
app = FastAPI(lifespan=lifespan, title=bot_config.BOT_NAME)

# Подключаем админ-панель
app.mount("/admin", admin_app)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def main_entry():
    """Точка входа"""
    try:
        await app.initialize()   # ← здесь была ошибка
        # Запуск веб-сервера (uvicorn запускается Render'ом)
        logger = logging.getLogger(__name__)
        logger.info("✅ Бот успешно инициализирован")
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.critical(f"Не удалось инициализировать приложение: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main_entry())
