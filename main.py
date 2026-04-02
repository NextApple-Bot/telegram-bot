# Файл: bot/db.py
import os
import asyncpg
import logging
import asyncio
from functools import wraps

from bot import config

logger = logging.getLogger(__name__)

_pool = None
_init_lock = asyncio.Lock()


def retry_on_db_error(retries=3, delay=1, backoff=2):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except (asyncpg.exceptions.ConnectionFailureError,
                        asyncpg.exceptions.InterfaceError,
                        asyncpg.exceptions.PostgresConnectionError) as e:
                    last_exception = e
                    if attempt < retries - 1:
                        wait = delay * (backoff ** attempt)
                        logger.warning(f"Ошибка БД (попытка {attempt+1}/{retries}): {e}. Повтор через {wait}с")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Все попытки исчерпаны: {e}")
                        raise
                except Exception as e:
                    raise
            raise last_exception
        return wrapper
    return decorator


async def get_pool():
    """Возвращает пул соединений, создавая его при необходимости.
    Теперь корректно пересоздаёт пул после close_pool().
    """
    global _pool
    if _pool is None:
        async with _init_lock:
            if _pool is None:  # двойная проверка
                _pool = await asyncpg.create_pool(
                    config.DATABASE_URL,
                    min_size=5,
                    max_size=20,
                    command_timeout=60,
                    max_inactive_connection_lifetime=300
                )
                logger.info("✅ Пул соединений создан")
    return _pool


async def close_pool():
    """Закрывает пул соединений и сбрасывает глобальную переменную."""
    global _pool
    if _pool:
        async with _init_lock:
            if _pool:
                await _pool.close()
                _pool = None
                logger.info("✅ Пул соединений закрыт и сброшен")


async def reset_pool():
    """Принудительно сбрасывает и пересоздаёт пул (для экстренных случаев)."""
    await close_pool()
    return await get_pool()
