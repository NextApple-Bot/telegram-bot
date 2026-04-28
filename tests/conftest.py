import asyncio
import pytest
from typing import AsyncGenerator, Dict, Any
import asyncpg
import os
from unittest.mock import AsyncMock, patch

from bot.db import get_pool, close_pool
from bot.services.cache import cache
from bot import config

# Переопределяем переменные окружения для тестов
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bot_test")
os.environ["REDIS_URL"] = ""  # отключаем Redis в тестах
os.environ["SCALING_ENABLED"] = "false"

# Перезагружаем конфиг
from importlib import reload
from bot import config as bot_config
reload(bot_config)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Создаёт таблицы в тестовой БД и очищает перед сессией."""
    pool = await asyncpg.create_pool(os.environ["TEST_DATABASE_URL"])
    async with pool.acquire() as conn:
        # Удаляем все таблицы (чистая БД)
        await conn.execute("DROP SCHEMA public CASCADE")
        await conn.execute("CREATE SCHEMA public")
        # Инициализируем БД через нашу функцию init_db
        from bot.db import init_db
        await init_db()
    await pool.close()
    yield
    # После тестов можно закрыть пул
    await close_pool()


@pytest.fixture
async def db_conn() -> AsyncGenerator:
    """Фикстура для получения соединения с БД в тесте."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


@pytest.fixture
def mock_bot():
    """Создаёт мок объекта Bot aiogram."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_document = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.react = AsyncMock()
    return bot


@pytest.fixture
def mock_state():
    """Мок FSMContext."""
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state
