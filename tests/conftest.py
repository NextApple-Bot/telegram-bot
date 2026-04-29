import os
from collections.abc import AsyncGenerator
from importlib import reload
from unittest.mock import AsyncMock

import asyncpg
import pytest

import bot.config as bot_config
from bot.db import close_pool, get_pool, init_db
from bot.services.cache import cache

# ------------------------------------------------------------
# 1. Переменные окружения и перезагрузка конфига
# ------------------------------------------------------------
TEST_DB_URL = "postgresql://postgres:postgres@localhost:5432/bot_test?sslmode=disable"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.setdefault("REDIS_URL", "")
os.environ["SCALING_ENABLED"] = "false"

reload(bot_config)

# ------------------------------------------------------------
# 2. Запрещаем uvloop (чтобы pytest‑asyncio использовал стандартный asyncio)
# ------------------------------------------------------------
os.environ["UVLOOP_NO_EXTENSIONS"] = "1"

@pytest.fixture(scope="session")
def event_loop():
    """Создаёт один event loop на всю сессию – обязательно для asyncpg."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """
    Один раз за сессию:
    – создаём свой пул (без SSL) и сбрасываем схему public
    – вызываем штатный init_db для создания всех таблиц
    – закрываем пул (дальше всё пойдёт через get_pool)
    """
    pool = await asyncpg.create_pool(
        TEST_DB_URL,
        min_size=1,
        max_size=5,
        ssl=False,
        command_timeout=30
    )
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await conn.execute("CREATE SCHEMA public")

    await init_db()          # создаёт глобальный пул в том же event loop
    await pool.close()
    yield
    await close_pool()


@pytest.fixture
async def db_conn() -> AsyncGenerator:
    """
    Выдаёт выделенное соединение из общего пула.
    Транзакция откатывается после теста для изоляции.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("BEGIN")
        try:
            yield conn
        finally:
            try:
                await conn.execute("ROLLBACK")
            except Exception:
                pass


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
