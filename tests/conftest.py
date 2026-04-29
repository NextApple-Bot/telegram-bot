# tests/conftest.py
import asyncio
import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import asyncpg
import pytest
from dotenv import load_dotenv

# Загружаем .env, если есть (не обязательно в CI)
load_dotenv()

# Явно задаём параметры подключения, отключающие SSL
TEST_DB_URL = "postgresql://postgres:postgres@localhost:5432/bot_test?sslmode=disable"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.setdefault("REDIS_URL", "")
os.environ["SCALING_ENABLED"] = "false"

# Перезагружаем конфиг после подмены
from importlib import reload
import bot.config as bot_config
reload(bot_config)

from bot.db import close_pool, get_pool, init_db
from bot.services.cache import cache


@pytest.fixture(scope="session")
def anyio_backend():
    """Указываем, что используем asyncio (для совместимости с pytest-asyncio)"""
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Создаёт чистую тестовую БД перед всеми тестами, отключая SSL."""
    pool = await asyncpg.create_pool(
        TEST_DB_URL,
        ssl=False,   # гарантированно отключаем SSL
        min_size=1,
        max_size=5
    )
    async with pool.acquire() as conn:
        # Полный сброс схемы
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")

    # Инициализируем таблицы через нашу функцию (она использует get_pool, который тоже будет без SSL)
    # Передаём SSL=False на уровне get_pool (см. правку в bot/db.py)
    await init_db()
    await pool.close()
    yield
    await close_pool()


@pytest.fixture
async def db_conn() -> AsyncGenerator:
    """Возвращает соединение из пула для теста (с отключённым SSL)."""
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
