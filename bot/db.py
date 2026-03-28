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
    global _pool
    if _pool is None:
        async with _init_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    config.DATABASE_URL,
                    min_size=5,
                    max_size=20,
                    command_timeout=60,
                    max_inactive_connection_lifetime=300
                )
                logger.info("✅ Пул соединений создан")
    return _pool

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ... (все существующие таблицы, включая sales, preorders, bookings, processed_messages и т.д.)
        # Добавляем новую таблицу для платежей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_payments (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL CHECK (type IN ('sale', 'preorder')),
                payment_type TEXT NOT NULL CHECK (payment_type IN ('cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment')),
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Индекс для быстрой очистки старых записей
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_daily_payments_created_at ON daily_payments(created_at)')
