import asyncio
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text

import redis.asyncio as aioredis

from bot.config import config

logger = logging.getLogger(__name__)


_async_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_redis_client: Optional[aioredis.Redis] = None
_lock = asyncio.Lock()


def get_async_engine() -> AsyncEngine:
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            config.DATABASE_URL,
            echo=config.DEBUG,
            pool_size=config.DB_POOL_SIZE,
            max_overflow=config.DB_POOL_MAX_OVERFLOW,
            pool_pre_ping=True,
        )
    return _async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _async_session_factory


async def init_db():
    """Инициализация базы данных."""
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: None)  # Прогрев
    logger.info("✅ База данных инициализирована")


async def close_db():
    """Закрытие соединений."""
    global _async_engine, _redis_client
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
    logger.info("✅ Соединения с БД и Redis закрыты")


def get_redis_client() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            config.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def check_db_health() -> dict:
    """Проверка здоровья базы данных и Redis."""
    result = {
        "database": False,
        "redis": False,
        "details": {}
    }

    # Проверка PostgreSQL
    try:
        engine = get_async_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        result["database"] = True
        result["details"]["database"] = "OK"
    except Exception as e:
        result["details"]["database"] = str(e)
        logger.error(f"Database health check failed: {e}")

    # Проверка Redis
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        result["redis"] = True
        result["details"]["redis"] = "OK"
    except Exception as e:
        result["details"]["redis"] = str(e)
        logger.error(f"Redis health check failed: {e}")

    return result