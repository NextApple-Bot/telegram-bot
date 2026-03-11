import aiosqlite
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
DB_PATH = "inventory.db"

async def init_db():
    """Создаёт таблицы, если их нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Существующие таблицы
        await db.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                serial TEXT,
                category_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                count INTEGER DEFAULT 1,
                cash REAL DEFAULT 0,
                terminal REAL DEFAULT 0,
                qr REAL DEFAULT 0,
                installment REAL DEFAULT 0,
                sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS preorders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cash REAL DEFAULT 0,
                terminal REAL DEFAULT 0,
                qr REAL DEFAULT 0,
                installment REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                total_amount REAL DEFAULT 0,
                booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
            )
        ''')

        # --- НОВЫЕ ТАБЛИЦЫ ---
        await db.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        await db.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                items_json TEXT,
                total_amount REAL,
                payment_details TEXT,
                purchase_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            )
        ''')

        await db.execute('CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_purchases_client ON purchases(client_id)')
        await db.commit()

# ---------- Существующие функции ----------

async def get_or_create_category(name: str) -> int:
    """
    Возвращает id категории.
    Ищет по нормализованному имени (нижний регистр, без двоеточия в конце).
    Если не найдено, создаёт новую категорию с переданным именем.
    """
    norm_name = name.lower().rstrip(':')
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id, name FROM categories')
        rows = await cursor.fetchall()
        for cat_id, cat_name in rows:
            if cat_name.lower().rstrip(':') == norm_name:
                return cat_id
        cursor = await db.execute('INSERT INTO categories (name) VALUES (?)', (name,))
        await db.commit()
        return cursor.lastrowid

async def add_item(text: str, serial: str = None, category_name: str = None):
    if category_name is None:
        category_name = "Общее:"
    cat_id = await get_or_create_category(category_name)
    # Нормализуем серийный номер
    normalized_serial = serial.strip().upper() if serial else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO items (text, serial, category_id) VALUES (?, ?, ?)',
            (text, normalized_serial, cat_id)
        )
        await db.commit()

async def get_item_id_by_serial(serial: str) -> int | None:
    """
    Возвращает id товара по серийному номеру.
    Поиск регистронезависимый, игнорируются пробелы в начале/конце.
    """
    if not serial:
        return None
    normalized = serial.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id FROM items WHERE UPPER(serial) = ?', (normalized,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def remove_item_by_serial(serial: str) -> int:
    normalized = serial.strip().upper() if serial else None
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('DELETE FROM items WHERE UPPER(serial) = ?', (normalized,))
        await db.commit()
        return cursor.rowcount

async def get_all_categories_with_items():
    """
    Возвращает список всех категорий с их товарами.
    Даже пустые категории включаются (с пустым списком items).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT c.id, c.name as category_name, i.text as item_text
            FROM categories c
            LEFT JOIN items i ON c.id = i.category_id
            ORDER BY c.id, i.id
        ''')
        rows = await cursor.fetchall()
        categories = {}
        for row in rows:
            cat = row['category_name']
            if cat not in categories:
                categories[cat] = []
            if row['item_text']:
                categories[cat].append(row['item_text'])
        result = [{"header": cat, "items": items} for cat, items in categories.items()]
        return result

async def get_items_grouped_by_category():
    """Возвращает только категории с товарами (для обратной совместимости)."""
    items = await get_all_categories_with_items()
    return [cat for cat in items if cat['items']]

async def add_sale(item_id: int = None, count: int = 1,
                   cash: float = 0, terminal: float = 0, qr: float = 0, installment: float = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO sales (item_id, count, cash, terminal, qr, installment) VALUES (?, ?, ?, ?, ?, ?)',
            (item_id, count, cash, terminal, qr, installment)
        )
        await db.commit()

async def add_preorder(cash=0, terminal=0, qr=0, installment=0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO preorders (cash, terminal, qr, installment) VALUES (?, ?, ?, ?)',
            (cash, terminal, qr, installment)
        )
        await db.commit()

async def add_booking(item_id: int, total_amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO bookings (item_id, total_amount) VALUES (?, ?)',
            (item_id, total_amount)
        )
        await db.commit()

async def get_today_stats():
    today = datetime.now().strftime('%Y-%m-%d')
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'SELECT COUNT(*), SUM(cash), SUM(terminal), SUM(qr), SUM(installment) FROM preorders WHERE DATE(created_at) = ?',
            (today,)
        )
        pre_count, pc, pt, pq, pi = await cursor.fetchone()
        pre_count = pre_count or 0
        pc = pc or 0
        pt = pt or 0
        pq = pq or 0
        pi = pi or 0

        cursor = await db.execute(
            'SELECT COUNT(*), SUM(total_amount) FROM bookings WHERE DATE(booked_at) = ?',
            (today,)
        )
        book_count, book_total = await cursor.fetchone()
        book_count = book_count or 0
        book_total = book_total or 0

        cursor = await db.execute(
            'SELECT COUNT(*), SUM(cash), SUM(terminal), SUM(qr), SUM(installment) FROM sales WHERE DATE(sold_at) = ?',
            (today,)
        )
        sale_count, sc, st, sq, si = await cursor.fetchone()
        sale_count = sale_count or 0
        sc = sc or 0
        st = st or 0
        sq = sq or 0
        si = si or 0

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

# ---------- ФУНКЦИЯ ДЛЯ ОБНОВЛЕНИЯ ТОВАРОВ В КАТЕГОРИИ ----------

async def update_category_items(category_name: str, new_items: list):
    """
    Заменяет все товары в указанной категории новым списком.
    Старые товары удаляются.
    Извлекает серийные номера из текста товаров и сохраняет их.
    """
    # Локальный импорт для избежания циклических зависимостей
    from inventory import extract_serial
    cat_id = await get_or_create_category(category_name)
    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем старые товары в этой категории
        await db.execute('DELETE FROM items WHERE category_id = ?', (cat_id,))
        # Вставляем новые товары
        for item_text in new_items:
            serial = extract_serial(item_text)
            if serial:
                serial = serial.strip().upper()
            await db.execute(
                'INSERT INTO items (text, serial, category_id) VALUES (?, ?, ?)',
                (item_text, serial, cat_id)
            )
        await db.commit()

# ---------- НОВЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С КЛИЕНТАМИ ----------

async def get_or_create_client(phone: str = None, phones: list = None, full_name: str = None,
                               telegram_username: str = None, social_network: str = None,
                               referral_source: str = None) -> int:
    logger.info(f"🔍 get_or_create_client: phone={phone}, phones={phones}, full_name={full_name}")
    async with aiosqlite.connect(DB_PATH) as db:
        if phone:
            cursor = await db.execute('SELECT id, full_name, telegram_username, social_network, referral_source, phones FROM clients WHERE phone = ?', (phone,))
            row = await cursor.fetchone()
            if row:
                client_id = row[0]
                logger.info(f"👤 Найден существующий клиент ID {client_id}")
                updates = []
                params = []
                if full_name and full_name != row[1]:
                    updates.append("full_name = ?")
                    params.append(full_name)
                if telegram_username and telegram_username != row[2]:
                    updates.append("telegram_username = ?")
                    params.append(telegram_username)
                if social_network and social_network != row[3]:
                    updates.append("social_network = ?")
                    params.append(social_network)
                if referral_source and referral_source != row[4]:
                    updates.append("referral_source = ?")
                    params.append(referral_source)
                if phones:
                    existing_phones = row[5] if row[5] else ""
                    all_phones = set(existing_phones.split(',')) if existing_phones else set()
                    all_phones.update(phones)
                    new_phones_str = ",".join(sorted(all_phones))
                    if new_phones_str != existing_phones:
                        updates.append("phones = ?")
                        params.append(new_phones_str)
                if updates:
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    query = f"UPDATE clients SET {', '.join(updates)} WHERE id = ?"
                    params.append(client_id)
                    await db.execute(query, params)
                    await db.commit()
                    logger.info(f"✅ Клиент {client_id} обновлён: {updates}")
                return client_id
            else:
                phones_str = ",".join(sorted(set(phones))) if phones else None
                logger.info(f"🆕 Создание нового клиента: phone={phone}, phones={phones_str}")
                cursor = await db.execute('''
                    INSERT INTO clients (full_name, phone, phones, telegram_username, social_network, referral_source)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (full_name, phone, phones_str, telegram_username, social_network, referral_source))
                await db.commit()
                return cursor.lastrowid
        else:
            phones_str = ",".join(sorted(set(phones))) if phones else None
            logger.info(f"🆕 Создание нового клиента без основного телефона: full_name={full_name}, phones={phones_str}")
            cursor = await db.execute('''
                INSERT INTO clients (full_name, phones, telegram_username, social_network, referral_source)
                VALUES (?, ?, ?, ?, ?)
            ''', (full_name, phones_str, telegram_username, social_network, referral_source))
            await db.commit()
            return cursor.lastrowid

async def add_purchase(client_id: int, items: list, total_amount: float, payment_details: dict, purchase_type: str = 'sale'):
    items_json = json.dumps(items, ensure_ascii=False)
    payment_json = json.dumps(payment_details, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO purchases (client_id, items_json, total_amount, payment_details, purchase_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (client_id, items_json, total_amount, payment_json, purchase_type))
        await db.commit()

async def get_client_purchases(client_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT * FROM purchases WHERE client_id = ? ORDER BY created_at DESC
        ''', (client_id,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def search_clients(query: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT * FROM clients 
            WHERE full_name LIKE ? OR phone LIKE ? OR telegram_username LIKE ?
            ORDER BY updated_at DESC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
