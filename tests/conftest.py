import os
import sys
from collections.abc import AsyncGenerator
from importlib import reload
from unittest.mock import AsyncMock, patch

# Блокируем uvloop до того, как он используется
try:
    import uvloop
    uvloop.install = lambda: None
except ImportError:
    pass

import asyncio
import asyncpg
import pytest

TEST_DB_URL = "postgresql://postgres:postgres@localhost:5432/bot_test?sslmode=disable"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.setdefault("REDIS_URL", "")
os.environ["SCALING_ENABLED"] = "false"

import bot.config as bot_config  # noqa: E402
reload(bot_config)

from bot.db import close_pool, init_db  # noqa: E402
from bot.services.cache import cache   # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    """Устанавливаем политику событийного цикла по умолчанию и создаём цикл."""
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_db_pool():
    """Создаёт сессионный пул с увеличенным таймаутом."""
    pool = await asyncpg.create_pool(
        TEST_DB_URL,
        min_size=1,
        max_size=5,
        ssl=False,
        command_timeout=30,
        timeout=10
    )
    yield pool
    await pool.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db(test_db_pool):
    """Сбрасывает и инициализирует тестовую БД один раз за сессию."""
    async with test_db_pool.acquire() as conn:
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")
    await init_db()

    async def _mock_get_pool():
        return test_db_pool

    with patch('bot.db.get_pool', new=_mock_get_pool):
        yield

    await close_pool()


@pytest.fixture
async def db_conn(test_db_pool) -> AsyncGenerator:
    """Выдаёт соединение с транзакцией."""
    async with test_db_pool.acquire() as conn:
        await conn.execute("BEGIN")
        try:
            yield conn
        finally:
            await conn.execute("ROLLBACK")


@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.send_document = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.react = AsyncMock()
    return bot


@pytest.fixture
def mock_state():
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


@pytest.fixture(autouse=True)
def disable_redis_cache():
    cache._enabled = False
    yield
    cache._enabled = bool(os.getenv("REDIS_URL"))
