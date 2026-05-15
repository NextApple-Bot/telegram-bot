import logging
import os
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

from bot.config import config

logger = logging.getLogger(__name__)

_async_engine = None
_async_session_factory = None


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        db_url = config.DATABASE_URL
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        _async_engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,           # важно для долгоживущих соединений
            pool_recycle=300,
            connect_args={"ssl": False if "localhost" in db_url else True},
        )
        logger.info("✅ Async engine создан")
    return _async_engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_async_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _async_session_factory


@asynccontextmanager
async def get_session() -> AsyncSession:
    """Удобный контекстный менеджер"""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        yield session


async def dispose_engine():
    global _async_engine, _async_session_factory
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None
        logger.info("✅ SQLAlchemy engine disposed")


async def check_db_health() -> bool:
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database healthcheck failed: {e}")
        return False


async def check_redis_health() -> bool:
    if not config.REDIS_URL:
        return True
    try:
        import redis.asyncio as redis
        r = redis.from_url(config.REDIS_URL, decode_responses=True)
        await r.ping()
        await r.aclose()
        return True
    except Exception as e:
        logger.warning(f"Redis healthcheck failed: {e}")
        return False
