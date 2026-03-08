import aiosqlite
from datetime import datetime

DB_PATH = "inventory.db"

async def init_db():
    """Создаёт таблицы, если их нет."""
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.commit()

# ---------- Категории и товары ----------

async def get_or_create_category(name: str) -> int:
    """Возвращает id категории, создаёт при необходимости."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id FROM categories WHERE name = ?', (name,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        cursor = await db.execute('INSERT INTO categories (name) VALUES (?)', (name,))
        await db.commit()
        return cursor.lastrowid

async def add_item(text: str, serial: str = None, category_name: str = None):
    """Добавляет товар. Если category_name не указана, использует 'Общее:'."""
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
    """Возвращает id товара по серийному номеру или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id FROM items WHERE serial = ?', (serial,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def remove_item_by_serial(serial: str) -> int:
    """Удаляет товар по серийному номеру. Возвращает количество удалённых."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('DELETE FROM items WHERE serial = ?', (serial,))
        await db.commit()
        return cursor.rowcount

async def get_all_items_with_categories():
    """
    Возвращает список товаров с названиями категорий.
    Важно: сортировка по items.id сохраняет порядок добавления товаров.
    """
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
    """
    Возвращает словарь {category_name: [items_text]}.
    Категории сохраняют порядок первого появления (по самому раннему товару в категории).
    """
    items = await get_all_items_with_categories()
    grouped = {}
    # Используем OrderedDict или просто словарь, но порядок сохранится в Python 3.7+
    for item in items:
        cat = item['category_name']
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(item['text'])
    return grouped

# ---------- Статистика ----------

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
    """Возвращает статистику за сегодня."""
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
