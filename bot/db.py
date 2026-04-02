# Файл: bot/db.py
import os
import asyncpg
import logging
import asyncio
from functools import wraps

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не задан в переменных окружения!")


# ---------- Декоратор для повторных попыток ----------
def retry_on_db_error(retries=3, delay=1, backoff=2):
    """
    Декоратор для асинхронных функций, выполняющих запросы к БД.
    При ошибках соединения повторяет вызов до retries раз.
    """
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
                    # Другие ошибки не повторяем
                    raise
            raise last_exception
        return wrapper
    return decorator


# ---------- Пул соединений с повторными попытками ----------
_pool = None

async def get_pool():
    """Возвращает пул соединений (создаёт при первом вызове с повторными попытками)."""
    global _pool
    if _pool is None:
        last_exception = None
        for attempt in range(5):  # до 5 попыток
            try:
                _pool = await asyncpg.create_pool(
                    DATABASE_URL,
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
    """Закрывает пул соединений."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("✅ Пул соединений закрыт")


async def init_db():
    """Создаёт таблицы и индексы, если их нет (синхронизирует с миграциями)."""
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
        # Таблица ежедневных платежей (финансы)
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

    logger.info("✅ Инициализация БД завершена (таблицы и индексы созданы)")


async def cleanup_old_records():
    """Фоновая задача: удаляет старые записи из processed_messages и daily_payments."""
    while True:
        try:
            await asyncio.sleep(86400)  # раз в сутки
            pool = await get_pool()
            async with pool.acquire() as conn:
                # Удаляем обработанные сообщения старше 30 дней
                res1 = await conn.execute('''
                    DELETE FROM processed_messages 
                    WHERE processed_at < NOW() - INTERVAL '30 days'
                ''')
                # Удаляем платежи старше 90 дней
                res2 = await conn.execute('''
                    DELETE FROM daily_payments 
                    WHERE created_at < NOW() - INTERVAL '90 days'
                ''')
                logger.info(f"Очистка БД: удалено processed_messages={res1.split()[1] if res1.startswith('DELETE') else 0}, "
                            f"daily_payments={res2.split()[1] if res2.startswith('DELETE') else 0}")
        except Exception as e:
            logger.exception(f"Ошибка при фоновой очистке БД: {e}")
