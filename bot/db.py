import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from bot.config import settings

_async_engine = None
_async_session_factory = None
_redis_client = None
_lock = asyncio.Lock()

async def get_async_engine():
    global _async_engine
    async with _lock:
        if _async_engine is None:
            _async_engine = create_async_engine(
                settings.DATABASE_URL,
                pool_size=int(settings.get('DB_POOL_SIZE', 10)),
                max_overflow=int(settings.get('DB_POOL_MAX_OVERFLOW', 5)),
                pool_timeout=30,
                pool_recycle=1800,
            )
    return _async_engine

async def get_async_session_factory():
    """Публичная функция для получения фабрики асинхронных сессий"""
    await get_async_engine()
    global _async_session_factory
    if _async_session_factory is None:
        engine = await get_async_engine()
        _async_session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _async_session_factory

async def init_db():
    engine = await get_async_engine()
    # ... alembic or metadata

async def close_db():
    global _async_engine
    if _async_engine:
        await _async_engine.dispose()

# Redis singleton
async def get_redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = ...  # your redis init
    return _redis_client
