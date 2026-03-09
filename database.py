import aiosqlite
import json
from datetime import datetime

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
                phone TEXT UNIQUE,                -- основной телефон для поиска
                phones TEXT,                       -- все телефоны через запятую
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
                items_json TEXT,          -- список товаров с ценами в JSON
                total_amount REAL,
                payment_details TEXT,     -- JSON с разбивкой по способам
                purchase_type TEXT,       -- 'sale', 'preorder', 'booking'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            )
        ''')

        # Индексы
        await db.execute('CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_purchases_client ON purchases(client_id)')
        await db.commit()

# ---------- Существующие функции ----------
async def get_or_create_category(name: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id FROM categories WHERE name = ?', (name,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        cursor = await db.execute('INSERT INTO categories (name) VALUES (?)', (name,))
        await db.commit()
        return cursor.lastrowid

async def add_item(text: str, serial: str = None, category_name: str = None):
    if category_name is None:
        category_name = "Общее:"
    cat_id = await get_or_create_category(category_name)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO items (text, serial, category_id) VALUES (?, ?, ?)',
            (text, serial, cat_id)
        )
        await db.commit()

async def get_item_id_by_serial(serial: str) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id FROM items WHERE serial = ?', (serial,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def remove_item_by_serial(serial: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('DELETE FROM items WHERE serial = ?', (serial,))
        await db.commit()
        return cursor.rowcount

async def get_all_items_with_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT items.*, categories.name as category_name
            FROM items
            JOIN categories ON items.category_id = categories.id
            ORDER BY items.id
        ''')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_items_grouped_by_category():
    items = await get_all_items_with_categories()
    grouped = {}
    for item in items:
        cat = item['category_name']
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(item['text'])
    return grouped

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
        # Предзаказы
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

        # Брони
        cursor = await db.execute(
            'SELECT COUNT(*), SUM(total_amount) FROM bookings WHERE DATE(booked_at) = ?',
            (today,)
        )
        book_count, book_total = await cursor.fetchone()
        book_count = book_count or 0
        book_total = book_total or 0

        # Продажи
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

# ---------- НОВЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С КЛИЕНТАМИ ----------

async def get_or_create_client(phone: str = None, phones: list = None, full_name: str = None,
                               telegram_username: str = None, social_network: str = None,
                               referral_source: str = None) -> int:
    """
    Возвращает ID клиента.
    phones: список всех найденных телефонов.
    phone: основной телефон (если есть) — первый из списка.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Если есть основной телефон, ищем по нему
        if phone:
            cursor = await db.execute('SELECT id, full_name, telegram_username, social_network, referral_source, phones FROM clients WHERE phone = ?', (phone,))
            row = await cursor.fetchone()
            if row:
                client_id = row[0]
                # Обновляем поля
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
                # Если есть новые телефоны и они отличаются от старых
                if phones:
                    existing_phones = row[5] if row[5] else ""
                    new_phones_str = ",".join(phones)
                    if new_phones_str != existing_phones:
                        updates.append("phones = ?")
                        params.append(new_phones_str)
                if updates:
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    query = f"UPDATE clients SET {', '.join(updates)} WHERE id = ?"
                    params.append(client_id)
                    await db.execute(query, params)
                    await db.commit()
                return client_id
            else:
                # Создаём нового
                phones_str = ",".join(phones) if phones else None
                cursor = await db.execute('''
                    INSERT INTO clients (full_name, phone, phones, telegram_username, social_network, referral_source)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (full_name, phone, phones_str, telegram_username, social_network, referral_source))
                await db.commit()
                return cursor.lastrowid
        else:
            # Без телефона создаём запись
            phones_str = ",".join(phones) if phones else None
            cursor = await db.execute('''
                INSERT INTO clients (full_name, phones, telegram_username, social_network, referral_source)
                VALUES (?, ?, ?, ?, ?)
            ''', (full_name, phones_str, telegram_username, social_network, referral_source))
            await db.commit()
            return cursor.lastrowid

async def add_purchase(client_id: int, items: list, total_amount: float, payment_details: dict, purchase_type: str = 'sale'):
    """
    Сохраняет запись о покупке.
    items: список словарей с ключами 'item_text', 'price' (если известна)
    payment_details: словарь с разбивкой по способам оплаты
    """
    items_json = json.dumps(items, ensure_ascii=False)
    payment_json = json.dumps(payment_details, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO purchases (client_id, items_json, total_amount, payment_details, purchase_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (client_id, items_json, total_amount, payment_json, purchase_type))
        await db.commit()

async def get_client_purchases(client_id: int):
    """Возвращает список покупок клиента."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT * FROM purchases WHERE client_id = ? ORDER BY created_at DESC
        ''', (client_id,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def search_clients(query: str):
    """Поиск клиентов по имени, телефону или username."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT * FROM clients 
            WHERE full_name LIKE ? OR phone LIKE ? OR telegram_username LIKE ?
            ORDER BY updated_at DESC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]                social_network TEXT,
                referral_source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                items_json TEXT,          -- список товаров с ценами в JSON
                total_amount REAL,
                payment_details TEXT,     -- JSON с разбивкой по способам
                purchase_type TEXT,       -- 'sale', 'preorder', 'booking'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
            )
        ''')

        # Индексы
        await db.execute('CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_purchases_client ON purchases(client_id)')
        await db.commit()

# ---------- Существующие функции (без изменений, но для полноты приведу) ----------

async def get_or_create_category(name: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id FROM categories WHERE name = ?', (name,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        cursor = await db.execute('INSERT INTO categories (name) VALUES (?)', (name,))
        await db.commit()
        return cursor.lastrowid

async def add_item(text: str, serial: str = None, category_name: str = None):
    if category_name is None:
        category_name = "Общее:"
    cat_id = await get_or_create_category(category_name)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO items (text, serial, category_id) VALUES (?, ?, ?)',
            (text, serial, cat_id)
        )
        await db.commit()

async def get_item_id_by_serial(serial: str) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id FROM items WHERE serial = ?', (serial,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def remove_item_by_serial(serial: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('DELETE FROM items WHERE serial = ?', (serial,))
        await db.commit()
        return cursor.rowcount

async def get_all_items_with_categories():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT items.*, categories.name as category_name
            FROM items
            JOIN categories ON items.category_id = categories.id
            ORDER BY items.id
        ''')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_items_grouped_by_category():
    items = await get_all_items_with_categories()
    grouped = {}
    for item in items:
        cat = item['category_name']
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(item['text'])
    return grouped

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
        # Предзаказы
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

        # Брони
        cursor = await db.execute(
            'SELECT COUNT(*), SUM(total_amount) FROM bookings WHERE DATE(booked_at) = ?',
            (today,)
        )
        book_count, book_total = await cursor.fetchone()
        book_count = book_count or 0
        book_total = book_total or 0

        # Продажи
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

# ---------- НОВЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С КЛИЕНТАМИ ----------

async def get_or_create_client(phone: str = None, full_name: str = None,
                               telegram_username: str = None, social_network: str = None,
                               referral_source: str = None) -> int:
    """
    Возвращает ID клиента.
    - Если телефон указан, ищет клиента по телефону.
      Если находит, обновляет остальные поля (передавая не None значения).
      Если не находит, создаёт нового клиента с указанными данными.
    - Если телефон не указан, создаёт нового клиента без телефона.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if phone:
            # Проверяем существование
            cursor = await db.execute('SELECT id, full_name, telegram_username, social_network, referral_source FROM clients WHERE phone = ?', (phone,))
            row = await cursor.fetchone()
            if row:
                client_id = row[0]
                # Обновляем поля, которые переданы и отличаются от текущих
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
                if updates:
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    query = f"UPDATE clients SET {', '.join(updates)} WHERE id = ?"
                    params.append(client_id)
                    await db.execute(query, params)
                    await db.commit()
                return client_id
            else:
                # Создаём нового
                cursor = await db.execute('''
                    INSERT INTO clients (full_name, phone, telegram_username, social_network, referral_source)
                    VALUES (?, ?, ?, ?, ?)
                ''', (full_name, phone, telegram_username, social_network, referral_source))
                await db.commit()
                return cursor.lastrowid
        else:
            # Без телефона создаём запись (телефон NULL)
            cursor = await db.execute('''
                INSERT INTO clients (full_name, telegram_username, social_network, referral_source)
                VALUES (?, ?, ?, ?)
            ''', (full_name, telegram_username, social_network, referral_source))
            await db.commit()
            return cursor.lastrowid

async def add_purchase(client_id: int, items: list, total_amount: float, payment_details: dict, purchase_type: str = 'sale'):
    """
    Сохраняет запись о покупке.
    items: список словарей с ключами 'item_text', 'price' (если известна)
    payment_details: словарь с разбивкой по способам оплаты
    """
    items_json = json.dumps(items, ensure_ascii=False)
    payment_json = json.dumps(payment_details, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO purchases (client_id, items_json, total_amount, payment_details, purchase_type)
            VALUES (?, ?, ?, ?, ?)
        ''', (client_id, items_json, total_amount, payment_json, purchase_type))
        await db.commit()

async def get_client_purchases(client_id: int):
    """Возвращает список покупок клиента."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT * FROM purchases WHERE client_id = ? ORDER BY created_at DESC
        ''', (client_id,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def search_clients(query: str):
    """Поиск клиентов по имени, телефону или username."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT * FROM clients 
            WHERE full_name LIKE ? OR phone LIKE ? OR telegram_username LIKE ?
            ORDER BY updated_at DESC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
