import re
import aiosqlite  # <--- ЭТО ВАЖНО! Добавьте этот импорт
from database import (
    add_item, remove_item_by_serial, get_items_grouped_by_category,
    get_or_create_category, get_item_id_by_serial, DB_PATH
)

UNIT_PATTERN = re.compile(r'^\d+\s*(mm|см|дюйм|gb|tb|mb|р|руб|\$|€|%|скидка|бонус)$', re.IGNORECASE)
TELEPHONE_PATTERN = re.compile(r'^\+?\d{10,11}$')

def extract_serial(line):
    """Извлекает серийный номер из строки товара."""
    matches = re.finditer(r'\(([A-Za-z0-9\-]{5,})\)', line)
    for match in matches:
        candidate = match.group(1)
        if re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            return candidate.upper()
        if candidate.isdigit() and len(candidate) >= 10:
            return candidate
    return None

def extract_serials_from_text(text):
    """Извлекает все серийные номера из текста."""
    serials = set()
    matches = re.finditer(r'\(([A-Za-z0-9\-]{5,})\)', text)
    for match in matches:
        candidate = match.group(1)
        if re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            serials.add(candidate.upper())
        elif candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
    return list(serials)

async def load_inventory():
    """Возвращает список категорий с товарами в формате [{"header": cat, "items": [...]}]."""
    grouped = await get_items_grouped_by_category()
    categories = []
    for cat_name, items in grouped.items():
        categories.append({"header": cat_name, "items": items})
    return categories

async def save_inventory(categories):
    """
    Полностью заменяет ассортимент новыми категориями.
    """
    # Очищаем таблицы
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM items')
        await db.execute('DELETE FROM categories')
        await db.commit()

    # Добавляем новые категории и товары
    for cat in categories:
        cat_id = await get_or_create_category(cat['header'])
        for item_text in cat['items']:
            serial = extract_serial(item_text)
            await add_item(item_text, serial, cat['header'])

async def remove_by_serial(serial: str) -> int:
    """Удаляет товар по серийному номеру."""
    return await remove_item_by_serial(serial)
