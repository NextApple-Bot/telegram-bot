import os
import asyncpg
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL не задан в переменных окружения!")

async def init_db():
    """Создаёт таблицы и индексы, если их нет."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                serial TEXT,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
                count INTEGER DEFAULT 1,
                cash REAL DEFAULT 0,
                terminal REAL DEFAULT 0,
                qr REAL DEFAULT 0,
                installment REAL DEFAULT 0,
                sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
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
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                total_amount REAL DEFAULT 0,
                booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
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
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_client ON purchases(client_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_categories_lower_name ON categories(LOWER(name))')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_serial ON items(serial)')
    finally:
        await conn.close()

# ---------- Категории и товары ----------

async def get_or_create_category(name: str) -> int:
    norm_name = name.lower().rstrip(':')
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow('SELECT id FROM categories WHERE LOWER(name) = $1', norm_name)
        if row:
            return row['id']
        row = await conn.fetchrow('INSERT INTO categories (name) VALUES ($1) RETURNING id', name)
        return row['id']
    finally:
        await conn.close()

async def add_item(text: str, serial: str = None, category_name: str = None):
    if category_name is None:
        category_name = "Общее:"
    cat_id = await get_or_create_category(category_name)
    normalized_serial = serial.strip().upper() if serial else None
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute('''
            INSERT INTO items (text, serial, category_id) VALUES ($1, $2, $3)
        ''', text, normalized_serial, cat_id)
    finally:
        await conn.close()

async def get_item_id_by_serial(serial: str) -> int | None:
    if not serial:
        return None
    normalized = serial.strip().upper()
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow('SELECT id FROM items WHERE UPPER(serial) = $1', normalized)
        return row['id'] if row else None
    finally:
        await conn.close()

async def get_item_by_serial(serial: str) -> dict | None:
    normalized = serial.strip().upper()
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow('''
            SELECT i.text, c.name as category_name
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE UPPER(i.serial) = $1
        ''', normalized)
        return dict(row) if row else None
    finally:
        await conn.close()

async def remove_item_by_serial(serial: str) -> int:
    normalized = serial.strip().upper() if serial else None
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        result = await conn.execute('DELETE FROM items WHERE UPPER(serial) = $1', normalized)
        return int(result.split()[1]) if result.startswith('DELETE') else 0
    finally:
        await conn.close()

async def get_all_categories_with_items():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
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
    finally:
        await conn.close()

async def get_all_items_serials():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch('SELECT text, serial FROM items')
        return [dict(row) for row in rows]
    finally:
        await conn.close()

async def get_items_grouped_by_category():
    items = await get_all_categories_with_items()
    return [cat for cat in items if cat['items']]

async def update_category_items(category_name: str, new_items: list):
    from inventory import extract_serial
    cat_id = await get_or_create_category(category_name)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        async with conn.transaction():
            await conn.execute('DELETE FROM items WHERE category_id = $1', cat_id)
            for item_text in new_items:
                serial = extract_serial(item_text)
                if serial:
                    serial = serial.strip().upper()
                await conn.execute('''
                    INSERT INTO items (text, serial, category_id) VALUES ($1, $2, $3)
                ''', item_text, serial, cat_id)
    finally:
        await conn.close()

async def get_item_by_text(text: str) -> dict | None:
    """Возвращает информацию о товаре по точному совпадению текста."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow('''
            SELECT i.text, c.name as category_name
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE i.text = $1
        ''', text)
        return dict(row) if row else None
    finally:
        await conn.close()

# ---------- Статистика ----------

async def add_sale(item_id: int = None, count: int = 1,
                   cash: float = 0, terminal: float = 0, qr: float = 0, installment: float = 0):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute('''
            INSERT INTO sales (item_id, count, cash, terminal, qr, installment)
            VALUES ($1, $2, $3, $4, $5, $6)
        ''', item_id, count, cash, terminal, qr, installment)
    finally:
        await conn.close()

async def add_preorder(cash=0, terminal=0, qr=0, installment=0):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute('''
            INSERT INTO preorders (cash, terminal, qr, installment)
            VALUES ($1, $2, $3, $4)
        ''', cash, terminal, qr, installment)
    finally:
        await conn.close()

async def add_booking(item_id: int, total_amount: float):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute('''
            INSERT INTO bookings (item_id, total_amount) VALUES ($1, $2)
        ''', item_id, total_amount)
    finally:
        await conn.close()

async def get_today_stats():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = await asyncpg.connect(DATABASE_URL)
    try:
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

        sale = await conn.fetchrow('''
            SELECT COUNT(*), COALESCE(SUM(cash),0), COALESCE(SUM(terminal),0),
                   COALESCE(SUM(qr),0), COALESCE(SUM(installment),0)
            FROM sales WHERE DATE(sold_at) = $1
        ''', today)
        sale_count, sc, st, sq, si = sale

        return {
            'date': today,
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
    finally:
        await conn.close()

# ---------- Клиенты и покупки ----------

async def get_or_create_client(phone: str = None, phones: list = None, full_name: str = None,
                               telegram_username: str = None, social_network: str = None,
                               referral_source: str = None) -> int:
    logger.info(f"🔍 get_or_create_client: phone={phone}, phones={phones}, full_name={full_name}")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
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
    finally:
        await conn.close()

async def add_purchase(client_id: int, items: list, total_amount: float, payment_details: dict, purchase_type: str = 'sale'):
    items_json = json.dumps(items, ensure_ascii=False)
    payment_json = json.dumps(payment_details, ensure_ascii=False)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute('''
            INSERT INTO purchases (client_id, items_json, total_amount, payment_details, purchase_type)
            VALUES ($1, $2, $3, $4, $5)
        ''', client_id, items_json, total_amount, payment_json, purchase_type)
    finally:
        await conn.close()

async def get_client_purchases(client_id: int):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch('SELECT * FROM purchases WHERE client_id = $1 ORDER BY created_at DESC', client_id)
        return [dict(row) for row in rows]
    finally:
        await conn.close()

async def search_clients(query: str):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch('''
            SELECT * FROM clients 
            WHERE full_name ILIKE $1 OR phone ILIKE $1 OR telegram_username ILIKE $1
            ORDER BY updated_at DESC
        ''', f'%{query}%')
        return [dict(row) for row in rows]
    finally:
        await conn.close()
