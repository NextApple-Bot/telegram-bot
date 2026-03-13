import os
import asyncpg
import json
import logging
import asyncio
from datetime import date, datetime
from functools import wraps

import config

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
                        asyncpg.exceptions.ConnectionDoesNotExistError,
                        asyncpg.exceptions.InterfaceError,
                        asyncpg.exceptions.ConnectionRejectionError,
                        asyncpg.exceptions.ConnectionNotInitializedError,
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

# ---------- Пул соединений ----------
_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=5,
            max_size=20,
            command_timeout=60,
            max_inactive_connection_lifetime=300
        )
        logger.info("✅ Пул соединений создан")
    return _pool

async def init_db():
    """Создаёт таблицы и индексы, если их нет."""
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
        # Индексы
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_client ON purchases(client_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_categories_lower_name ON categories(LOWER(name))')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_serial ON items(serial)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_created_at ON clients(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_created_at ON purchases(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_is_booked ON items(is_booked)')

# ---------- Категории и товары ----------

@retry_on_db_error()
async def get_or_create_category(name: str) -> int:
    norm_name = name.lower().rstrip(':')
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT id FROM categories WHERE LOWER(name) = $1', norm_name)
        if row:
            return row['id']
        row = await conn.fetchrow('INSERT INTO categories (name) VALUES ($1) RETURNING id', name)
        return row['id']

@retry_on_db_error()
async def add_item(text: str, serial: str = None, category_name: str = None):
    if category_name is None:
        category_name = "Общее:"
    cat_id = await get_or_create_category(category_name)
    normalized_serial = serial.strip().upper() if serial else None
    is_booked = 'Бронь от' in text
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO items (text, serial, category_id, is_booked)
            VALUES ($1, $2, $3, $4)
        ''', text, normalized_serial, cat_id, is_booked)

@retry_on_db_error()
async def get_item_id_by_serial(serial: str) -> int | None:
    if not serial:
        return None
    normalized = serial.strip().upper()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT id FROM items WHERE UPPER(serial) = $1', normalized)
        return row['id'] if row else None

@retry_on_db_error()
async def get_item_by_serial(serial: str) -> dict | None:
    normalized = serial.strip().upper()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''
            SELECT i.text, c.name as category_name
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE UPPER(i.serial) = $1
        ''', normalized)
        return dict(row) if row else None

@retry_on_db_error()
async def get_item_by_text(text: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('''
            SELECT i.text, c.name as category_name
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE i.text = $1
        ''', text)
        return dict(row) if row else None

@retry_on_db_error()
async def remove_item_by_serial(serial: str) -> int:
    normalized = serial.strip().upper() if serial else None
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute('DELETE FROM items WHERE UPPER(serial) = $1', normalized)
        return int(result.split()[1]) if result.startswith('DELETE') else 0

@retry_on_db_error()
async def get_all_categories_with_items():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT c.name as category_name, i.text as item_text
            FROM categories c
            LEFT JOIN items i ON c.id = i.category_id
            ORDER BY c.id, i.id
        ''')
        categories = {}
        for row in rows:
            cat = row['category_name']
            if cat not in categories:
                categories[cat] = []
            if row['item_text']:
                categories[cat].append(row['item_text'])
        return [{"header": cat, "items": items} for cat, items in categories.items()]

@retry_on_db_error()
async def get_all_items_serials():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT text, serial FROM items')
        return [dict(row) for row in rows]

async def update_category_items(category_name: str, new_items: list):
    from serial_utils import extract_serial
    cat_id = await get_or_create_category(category_name)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('DELETE FROM items WHERE category_id = $1', cat_id)
            for item_text in new_items:
                serial = extract_serial(item_text)
                if serial:
                    serial = serial.strip().upper()
                is_booked = 'Бронь от' in item_text
                await conn.execute('''
                    INSERT INTO items (text, serial, category_id, is_booked)
                    VALUES ($1, $2, $3, $4)
                ''', item_text, serial, cat_id, is_booked)

@retry_on_db_error()
async def clear_all_inventory():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM categories')

# ---------- Статистика ----------

@retry_on_db_error()
async def add_sale(item_id: int = None, count: int = 1,
                   cash: float = 0, terminal: float = 0, qr: float = 0, installment: float = 0,
                   is_accessory: bool = False):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO sales (item_id, count, cash, terminal, qr, installment, is_accessory)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        ''', item_id, count, cash, terminal, qr, installment, is_accessory)

@retry_on_db_error()
async def add_preorder(cash=0, terminal=0, qr=0, installment=0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO preorders (cash, terminal, qr, installment)
            VALUES ($1, $2, $3, $4)
        ''', cash, terminal, qr, installment)

@retry_on_db_error()
async def add_booking(item_id: int, total_amount: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO bookings (item_id, total_amount) VALUES ($1, $2)
        ''', item_id, total_amount)

@retry_on_db_error()
async def get_today_stats():
    today = date.today()
    pool = await get_pool()
    async with pool.acquire() as conn:
        sale_count = await conn.fetchval('''
            SELECT COUNT(*) FROM sales WHERE DATE(sold_at) = $1 AND is_accessory = false
        ''', today) or 0

        sale_sums = await conn.fetchrow('''
            SELECT COALESCE(SUM(cash),0), COALESCE(SUM(terminal),0),
                   COALESCE(SUM(qr),0), COALESCE(SUM(installment),0)
            FROM sales WHERE DATE(sold_at) = $1
        ''', today)
        sc, st, sq, si = sale_sums

        pre = await conn.fetchrow('''
            SELECT COUNT(*), COALESCE(SUM(cash),0), COALESCE(SUM(terminal),0),
                   COALESCE(SUM(qr),0), COALESCE(SUM(installment),0)
            FROM preorders WHERE DATE(created_at) = $1
        ''', today)
        pre_count, pc, pt, pq, pi = pre

        book = await conn.fetchrow('''
            SELECT COUNT(*), COALESCE(SUM(total_amount),0)
            FROM bookings WHERE DATE(booked_at) = $1
        ''', today)
        book_count, book_total = book

        return {
            'date': today.strftime('%Y-%m-%d'),
            'preorders': pre_count,
            'bookings': book_count,
            'sales': sale_count,
            'preorders_cash': pc,
            'preorders_terminal': pt,
            'preorders_qr': pq,
            'preorders_installment': pi,
            'bookings_total': book_total,
            'sales_cash': sc,
            'sales_terminal': st,
            'sales_qr': sq,
            'sales_installment': si,
        }

# ---------- Клиенты и покупки ----------

@retry_on_db_error()
async def get_or_create_client(phone: str = None, phones: list = None, full_name: str = None,
                               telegram_username: str = None, social_network: str = None,
                               referral_source: str = None) -> int:
    logger.info(f"🔍 get_or_create_client: phone={phone}, phones={phones}, full_name={full_name}")
    pool = await get_pool()
    async with pool.acquire() as conn:
        if phone:
            row = await conn.fetchrow('SELECT id, full_name, telegram_username, social_network, referral_source, phones FROM clients WHERE phone = $1', phone)
            if row:
                client_id = row['id']
                updates = []
                params = []
                if full_name and full_name != row['full_name']:
                    updates.append("full_name = $" + str(len(params)+1))
                    params.append(full_name)
                if telegram_username and telegram_username != row['telegram_username']:
                    updates.append("telegram_username = $" + str(len(params)+1))
                    params.append(telegram_username)
                if social_network and social_network != row['social_network']:
                    updates.append("social_network = $" + str(len(params)+1))
                    params.append(social_network)
                if referral_source and referral_source != row['referral_source']:
                    updates.append("referral_source = $" + str(len(params)+1))
                    params.append(referral_source)
                if phones:
                    existing_phones = row['phones'] if row['phones'] else ""
                    all_phones = set(existing_phones.split(',')) if existing_phones else set()
                    all_phones.update(phones)
                    new_phones_str = ",".join(sorted(all_phones))
                    if new_phones_str != existing_phones:
                        updates.append("phones = $" + str(len(params)+1))
                        params.append(new_phones_str)
                if updates:
                    set_clause = ", ".join(updates)
                    params.append(client_id)
                    query = f"UPDATE clients SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ${len(params)}"
                    await conn.execute(query, *params)
                    logger.info(f"✅ Клиент {client_id} обновлён")
                return client_id
            else:
                phones_str = ",".join(sorted(set(phones))) if phones else None
                row = await conn.fetchrow('''
                    INSERT INTO clients (full_name, phone, phones, telegram_username, social_network, referral_source)
                    VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
                ''', full_name, phone, phones_str, telegram_username, social_network, referral_source)
                return row['id']
        else:
            phones_str = ",".join(sorted(set(phones))) if phones else None
            row = await conn.fetchrow('''
                INSERT INTO clients (full_name, phones, telegram_username, social_network, referral_source)
                VALUES ($1, $2, $3, $4, $5) RETURNING id
            ''', full_name, phones_str, telegram_username, social_network, referral_source)
            return row['id']

@retry_on_db_error()
async def add_purchase(client_id: int, items: list, total_amount: float, payment_details: dict, purchase_type: str = 'sale'):
    items_json = json.dumps(items, ensure_ascii=False)
    payment_json = json.dumps(payment_details, ensure_ascii=False)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO purchases (client_id, items_json, total_amount, payment_details, purchase_type)
            VALUES ($1, $2, $3, $4, $5)
        ''', client_id, items_json, total_amount, payment_json, purchase_type)

@retry_on_db_error()
async def get_client_purchases(client_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM purchases WHERE client_id = $1 ORDER BY created_at DESC', client_id)
        return [dict(row) for row in rows]

@retry_on_db_error()
async def search_clients(query: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT * FROM clients 
            WHERE full_name ILIKE $1 OR phone ILIKE $1 OR telegram_username ILIKE $1
            ORDER BY updated_at DESC
        ''', f'%{query}%')
        return [dict(row) for row in rows]

# ---------- Функции для работы по месяцам ----------

@retry_on_db_error()
async def get_available_months():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows1 = await conn.fetch('''
            SELECT DISTINCT to_char(created_at, 'MM.YYYY') as month
            FROM clients
            WHERE created_at IS NOT NULL
        ''')
        rows2 = await conn.fetch('''
            SELECT DISTINCT to_char(created_at, 'MM.YYYY') as month
            FROM purchases
            WHERE created_at IS NOT NULL
        ''')
        months = sorted(set([r['month'] for r in rows1] + [r['month'] for r in rows2]), reverse=True)
        return months

@retry_on_db_error()
async def get_clients_data_for_month(month_str: str):
    month, year = map(int, month_str.split('.'))
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date()
    else:
        end_date = datetime(year, month + 1, 1).date()

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT 
                c.id as client_id,
                c.full_name,
                c.phone,
                c.phones,
                c.telegram_username,
                c.social_network,
                c.referral_source,
                c.created_at as client_created_at,
                p.id as purchase_id,
                p.items_json,
                p.total_amount,
                p.payment_details,
                p.purchase_type,
                p.created_at as purchase_created_at
            FROM clients c
            LEFT JOIN purchases p ON c.id = p.client_id 
                AND p.created_at >= $1 AND p.created_at < $2
            WHERE (p.id IS NOT NULL) OR (c.created_at >= $1 AND c.created_at < $2)
            ORDER BY c.id, p.created_at
        ''', start_date, end_date)
        return [dict(row) for row in rows]
