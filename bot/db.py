# Файл: bot/db.py
import os
import asyncpg
import logging
import asyncio
from functools import wraps

from bot import config

logger = logging.getLogger(__name__)


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


_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        last_exception = None
        for attempt in range(5):
            try:
                _pool = await asyncpg.create_pool(
                    config.DATABASE_URL,
                    min_size=2,
                    max_size=10,
                    command_timeout=60,
                    max_inactive_connection_lifetime=300
                )
                logger.info("✅ Пул соединений создан")
                break
            except Exception as e:
                last_exception = e
                wait = 2 ** attempt
                logger.warning(f"Не удалось создать пул (попытка {attempt+1}/5): {e}. Повтор через {wait}с")
                await asyncio.sleep(wait)
        else:
            logger.error("Все попытки создания пула провалились")
            raise last_exception
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("✅ Пул соединений закрыт")


# Файл: bot/db.py (исправленная функция init_db)

async def init_db():
    """Создаёт все таблицы, индексы и недостающие колонки."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ... (все CREATE TABLE, индексы и ALTER остаются без изменений) ...
        
        # Добавление колонок для брони и продажи (уже есть)
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_price FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_prepayment FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_platform VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_full_name VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_phone VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_price FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_prepayment FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_payment_type VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_platform VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_full_name VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_phone VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_payment_amount FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS is_sold BOOLEAN DEFAULT FALSE')
        await conn.execute('ALTER TABLE daily_payments ADD COLUMN IF NOT EXISTS sale_message_id BIGINT')
        
        # НОВАЯ СТРОКА – ПРАВИЛЬНЫЙ ОТСТУП (4 пробела)
        await conn.execute('ALTER TABLE deleted_items ADD COLUMN IF NOT EXISTS sale_message_id BIGINT')

    logger.info("✅ Инициализация БД завершена (таблицы, индексы и колонки созданы)")
        # Индексы
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_client ON purchases(client_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_categories_lower_name ON categories(LOWER(name))')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_serial ON items(serial)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_created_at ON clients(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_created_at ON purchases(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_is_booked ON items(is_booked)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_deleted_items_deleted_at ON deleted_items(deleted_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_deleted_items_restored ON deleted_items(restored)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_daily_payments_created_at ON daily_payments(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_processed_messages_processed_at ON processed_messages(processed_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_sales_item_id ON sales(item_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_created_at ON purchases(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_updated_at ON clients(updated_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_daily_payments_type ON daily_payments(type)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_processed_messages_chat_processed ON processed_messages(chat_id, processed_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_category_booked_created ON items(category_id, is_booked, created_at)')

        # Добавление новых колонок, если их нет (для совместимости)
        await conn.execute('''
            ALTER TABLE preorders 
            ADD COLUMN IF NOT EXISTS transfer REAL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS invoice REAL DEFAULT 0
        ''')
        await conn.execute('''
            ALTER TABLE sales 
            ADD COLUMN IF NOT EXISTS transfer REAL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS invoice REAL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS message_id BIGINT UNIQUE
        ''')
        await conn.execute('''
            ALTER TABLE purchases 
            ALTER COLUMN payment_details TYPE JSONB USING payment_details::jsonb
        ''')
        # Колонки для брони
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_price FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_prepayment FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_platform VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_full_name VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_phone VARCHAR')
        # Колонки для продажи через админку
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_price FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_prepayment FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_payment_type VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_platform VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_full_name VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_phone VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_payment_amount FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS is_sold BOOLEAN DEFAULT FALSE')
        # Колонка для связи daily_payments с продажей (для точного восстановления)
        await conn.execute('ALTER TABLE daily_payments ADD COLUMN IF NOT EXISTS sale_message_id BIGINT')

    logger.info("✅ Инициализация БД завершена (таблицы, индексы и колонки созданы)")


async def cleanup_old_records():
    """Фоновая задача: удаляет старые записи из processed_messages и daily_payments."""
    while True:
        await asyncio.sleep(86400)
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                res1 = await conn.execute('DELETE FROM processed_messages WHERE processed_at < NOW() - INTERVAL \'30 days\'')
                res2 = await conn.execute('DELETE FROM daily_payments WHERE created_at < NOW() - INTERVAL \'90 days\'')
                logger.info(f"Очистка БД: удалено processed_messages={res1.split()[1] if res1.startswith('DELETE') else 0}, daily_payments={res2.split()[1] if res2.startswith('DELETE') else 0}")
        except Exception as e:
            logger.exception(f"Ошибка при фоновой очистке БД: {e}")


async def cleanup_sold_periodically():
    """Фоновая задача: раз в сутки удаляет записи о проданных товарах старше 7 дней."""
    from datetime import datetime, timedelta
    while True:
        await asyncio.sleep(86400)
        try:
            pool = await get_pool()
            cutoff = datetime.now() - timedelta(days=7)
            async with pool.acquire() as conn:
                result = await conn.execute("DELETE FROM deleted_items WHERE reason = 'sale_from_admin' AND deleted_at < $1", cutoff)
                deleted = result.split()[1] if result.startswith('DELETE') else 0
                logger.info(f"Очистка продаж: удалено {deleted} записей старше 7 дней")
        except Exception as e:
            logger.exception(f"Ошибка при очистке продаж: {e}")
