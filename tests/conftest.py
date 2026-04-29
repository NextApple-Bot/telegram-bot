import os
from collections.abc import AsyncGenerator
from importlib import reload
from unittest.mock import AsyncMock

import asyncpg
import pytest
from dotenv import load_dotenv

import bot.config as bot_config
from bot.db import close_pool, get_pool, init_db
from bot.services.cache import cache

# Загружаем .env (в CI не обязателен, но не мешает)
load_dotenv()

# Принудительно задаём тестовую БД с отключением SSL
TEST_DB_URL = "postgresql://postgres:postgres@localhost:5432/bot_test?sslmode=disable"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.setdefault("REDIS_URL", "")
os.environ["SCALING_ENABLED"] = "false"

# Перезагружаем конфиг после подмены переменных
reload(bot_config)


@pytest.fixture(scope="session")
def anyio_backend():
    """Указываем бэкенд asyncio для pytest-asyncio"""
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Создаёт чистую тестовую БД перед всеми тестами (без SSL)."""
    pool = await asyncpg.create_pool(
        TEST_DB_URL,
        ssl=False,               # гарантированно без SSL
        min_size=1,
        max_size=5
    )
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")

    # Инициализируем таблицы (внутри используется get_pool, который тоже без SSL)
    await init_db()
    await pool.close()

    yield

    await close_pool()


@pytest.fixture
async def db_conn() -> AsyncGenerator:
    """Предоставляет соединение из пула для теста."""
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
    """Отключает Redis в тестах."""
    cache._enabled = False
    yield
    cache._enabled = bool(os.getenv("REDIS_URL"))
