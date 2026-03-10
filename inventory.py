import re
import aiosqlite
from database import (
    add_item, remove_item_by_serial, get_all_categories_with_items,
    get_or_create_category, DB_PATH, update_category_items
)

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
    """Возвращает список ВСЕХ категорий с товарами (включая пустые)."""
    categories = await get_all_categories_with_items()
    return categories

async def save_inventory(categories):
    """
    Обновляет ассортимент, сохраняя все существующие категории.
    - Категории, указанные в categories, обновляются (старые товары заменяются новыми).
    - Категории, не указанные, остаются без изменений (вместе со своими товарами).
    - Новые категории создаются.
    """
    for cat in categories:
        cat_name = cat['header']
        items = cat['items']
        await update_category_items(cat_name, items)

    # Категории, которых нет в новом списке, остаются нетронутыми

async def remove_by_serial(serial: str) -> int:
    """Удаляет товар по серийному номеру."""
    return await remove_item_by_serial(serial)
