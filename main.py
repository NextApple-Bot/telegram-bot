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


async def init_db():
    """Создаёт все таблицы, индексы и недостающие колонки."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Таблица категорий
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        ''')
        # Таблица товаров
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                serial TEXT,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                is_booked BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица продаж
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
                count INTEGER DEFAULT 1,
                cash REAL DEFAULT 0,
                terminal REAL DEFAULT 0,
                qr REAL DEFAULT 0,
                transfer REAL DEFAULT 0,
                invoice REAL DEFAULT 0,
                installment REAL DEFAULT 0,
                is_accessory BOOLEAN DEFAULT FALSE,
                message_id BIGINT UNIQUE,
                sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица предзаказов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS preorders (
                id SERIAL PRIMARY KEY,
                cash REAL DEFAULT 0,
                terminal REAL DEFAULT 0,
                qr REAL DEFAULT 0,
                transfer REAL DEFAULT 0,
                invoice REAL DEFAULT 0,
                installment REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица броней
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                total_amount REAL DEFAULT 0,
                booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица клиентов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                full_name TEXT,
                phone TEXT UNIQUE,
                phones TEXT,
                telegram_username TEXT,
                social_network TEXT,
                referral_source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица покупок
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                items_json TEXT,
                total_amount REAL,
                payment_details JSONB,
                purchase_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица удалённых товаров
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS deleted_items (
                id SERIAL PRIMARY KEY,
                item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
                text TEXT NOT NULL,
                serial TEXT,
                category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                restored BOOLEAN DEFAULT FALSE,
                reason TEXT
            )
        ''')
        # Таблица обработанных сообщений
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                message_id INTEGER NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, message_id)
            )
        ''')
        # Таблица ежедневных платежей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_payments (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL,
                payment_type TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CHECK (type IN ('sale', 'preorder')),
                CHECK (payment_type IN ('cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment'))
            )
        ''')
        
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

        # Добавление новых колонок (совместимость)
        await conn.execute('ALTER TABLE preorders ADD COLUMN IF NOT EXISTS transfer REAL DEFAULT 0')
        await conn.execute('ALTER TABLE preorders ADD COLUMN IF NOT EXISTS invoice REAL DEFAULT 0')
        await conn.execute('ALTER TABLE sales ADD COLUMN IF NOT EXISTS transfer REAL DEFAULT 0')
        await conn.execute('ALTER TABLE sales ADD COLUMN IF NOT EXISTS invoice REAL DEFAULT 0')
        await conn.execute('ALTER TABLE sales ADD COLUMN IF NOT EXISTS message_id BIGINT UNIQUE')
        await conn.execute('ALTER TABLE purchases ALTER COLUMN payment_details TYPE JSONB USING payment_details::jsonb')
        
        # Колонки брони
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_price FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_prepayment FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_platform VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_full_name VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_phone VARCHAR')
        
        # Колонки продажи
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_price FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_prepayment FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_payment_type VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_platform VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_full_name VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_phone VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_payment_amount FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS is_sold BOOLEAN DEFAULT FALSE')
        
        # Колонки для связи финансов и продажи
        await conn.execute('ALTER TABLE daily_payments ADD COLUMN IF NOT EXISTS sale_message_id BIGINT')
        
        # НОВАЯ КОЛОНКА ДЛЯ DELETED_ITEMS (ПРАВИЛЬНЫЙ ОТСТУП)
        await conn.execute('ALTER TABLE deleted_items ADD COLUMN IF NOT EXISTS sale_message_id BIGINT')

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
