import os
from collections.abc import AsyncGenerator
from importlib import reload
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

# ------------------------------------------------------------
# 1. Запрещаем uvloop до его использования
# ------------------------------------------------------------
try:
    import uvloop
    uvloop.install = lambda: None
except ImportError:
    pass

# ------------------------------------------------------------
# 2. Окружение и конфиг
# ------------------------------------------------------------
TEST_DB_URL = "postgresql://postgres:postgres@localhost:5432/bot_test?sslmode=disable"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ.setdefault("REDIS_URL", "")
os.environ["SCALING_ENABLED"] = "false"

import bot.config as bot_config  # noqa: E402 (переменные окружения заданы до импорта)

reload(bot_config)

from bot.db import close_pool, init_db  # noqa: E402 (зависит от bot_config)
from bot.services.cache import cache   # noqa: E402


# ------------------------------------------------------------
# 3. Единый тестовый пул (сессионный)
# ------------------------------------------------------------
@pytest.fixture(scope="session")
async def test_db_pool():
    """Создаёт сессионный пул, который будет использоваться во всех тестах."""
    pool = await asyncpg.create_pool(
        TEST_DB_URL,
        min_size=1,
        max_size=5,
        ssl=False,
        command_timeout=30
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

    # --- Подменяем глобальный get_pool на наш тестовый пул ---
    # Теперь любые вызовы get_pool() внутри тестов будут возвращать этот пул
    async def _mock_get_pool():
        return test_db_pool

    with patch('bot.db.get_pool', new=_mock_get_pool):
        yield

    # После тестов закрываем глобальный пул (он же test_db_pool)
    await close_pool()


# ------------------------------------------------------------
# 4. Фикстура соединения с транзакцией
# ------------------------------------------------------------
@pytest.fixture
async def db_conn(test_db_pool) -> AsyncGenerator:
    """Выдаёт соединение с изоляцией транзакцией."""
    async with test_db_pool.acquire() as conn:
        await conn.execute("BEGIN")
        try:
            yield conn
        finally:
            try:
                await conn.execute("ROLLBACK")
            except Exception:
                pass


# ------------------------------------------------------------
# 5. Моки
# ------------------------------------------------------------
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


# ------------------------------------------------------------
# 6. Отключение Redis в тестах
# ------------------------------------------------------------
@pytest.fixture(autouse=True)
def disable_redis_cache():
    cache._enabled = False
    yield
    cache._enabled = bool(os.getenv("REDIS_URL"))
