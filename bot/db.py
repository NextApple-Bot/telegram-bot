import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from redis.asyncio import Redis
from bot.config import settings

_async_engine = None
_async_session_factory = None
_redis_client: Redis | None = None
_lock = asyncio.Lock()

async def get_async_engine():
    global _async_engine
    async with _lock:
        if _async_engine is None:
            _async_engine = create_async_engine(
                settings.DATABASE_URL,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_POOL_MAX_OVERFLOW,
                pool_timeout=30,
                pool_recycle=1800,
                echo=settings.DEBUG,
            )
    return _async_engine


async def get_async_session_factory():
    """Публичная функция для получения фабрики сессий"""
    global _async_session_factory
    if _async_session_factory is None:
        engine = await get_async_engine()
        _async_session_factory = async_sessionmaker(
            engine, expire_on_commit=False
        )
    return _async_session_factory


async def init_db():
    """Инициализация БД (вызывается при старте)"""
    await get_async_engine()  # прогреваем engine


async def close_db():
    global _async_engine, _redis_client
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


# Redis
async def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
        )
    return _redis_client