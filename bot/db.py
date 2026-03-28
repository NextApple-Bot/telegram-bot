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
                payment_details TEXT,
                purchase_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица удалённых товаров (для Undo)
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
        # Таблица обработанных сообщений (идемпотентность)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, message_id)
            )
        ''')
        # Индексы (без транзакций)
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_client ON purchases(client_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_categories_lower_name ON categories(LOWER(name))')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_serial ON items(serial)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_created_at ON clients(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_created_at ON purchases(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_is_booked ON items(is_booked)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_deleted_items_deleted_at ON deleted_items(deleted_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_deleted_items_restored ON deleted_items(restored)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales(sold_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_preorders_created_at ON preorders(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_bookings_booked_at ON bookings(booked_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_processed_messages_lookup ON processed_messages(chat_id, message_id)')

        # Добавление колонок для совместимости
        await conn.execute('''
            ALTER TABLE preorders 
            ADD COLUMN IF NOT EXISTS transfer REAL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS invoice REAL DEFAULT 0
        ''')
        await conn.execute('''
            ALTER TABLE sales 
            ADD COLUMN IF NOT EXISTS transfer REAL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS invoice REAL DEFAULT 0
        ''')
