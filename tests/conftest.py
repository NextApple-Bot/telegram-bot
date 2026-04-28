import asyncio
import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import asyncpg
import pytest

from bot.db import close_pool, get_pool, init_db
from bot.services.cache import cache

# Переопределяем переменные окружения для тестов
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/bot_test")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("SCALING_ENABLED", "false")

# Перезагружаем конфиг после изменения переменных
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
    """Создаёт чистую тестовую БД перед запуском всех тестов."""
    test_db_url = os.environ["DATABASE_URL"]
    pool = await asyncpg.create_pool(test_db_url)
    async with pool.acquire() as conn:
        # Сбрасываем схему
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")
        # Инициализируем таблицы через init_db
        await init_db()
    await pool.close()
    yield
    await close_pool()


@pytest.fixture
async def db_conn() -> AsyncGenerator:
    """Возвращает соединение с БД для теста."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


@pytest.fixture
def mock_bot():
    """Мок aiogram Bot."""
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


@pytest.fixture(autouse=True)
def disable_redis_cache():
    """Отключает Redis в тестах (используем пустую реализацию)."""
    cache._enabled = False
    yield
    cache._enabled = bool(os.getenv("REDIS_URL"))
