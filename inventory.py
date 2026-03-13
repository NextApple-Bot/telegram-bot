import re
from database import (
    add_item, remove_item_by_serial, get_all_categories_with_items,
    get_or_create_category, update_category_items
)

def extract_serial(line):
    """
    Извлекает серийный номер из строки товара.
    - Если в скобках есть символ '№', возвращает всё содержимое скобок.
    - Иначе ищет комбинацию букв и цифр (длиной от 5 символов) или длинное число (≥10 цифр).
    """
    matches = re.finditer(r'\(([^)]+)\)', line)
    for match in matches:
        candidate = match.group(1).strip()
        if '№' in candidate:
            return candidate.upper()
        if re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            if len(candidate) >= 5:
                return candidate.upper()
        if candidate.isdigit() and len(candidate) >= 10:
            return candidate
    return None

def extract_serials_from_text(text):
    serials = set()
    matches = re.finditer(r'\(([^)]+)\)', text)
    for match in matches:
        candidate = match.group(1).strip()
        if '№' in candidate:
            serials.add(candidate.upper())
        elif re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            if len(candidate) >= 5:
                serials.add(candidate.upper())
        elif candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
    return list(serials)

async def load_inventory():
    categories = await get_all_categories_with_items()
    return categories

async def save_inventory(categories):
    for cat in categories:
        cat_name = cat['header']
        items = cat['items']
        await update_category_items(cat_name, items)

async def remove_by_serial(serial: str) -> int:
    return await remove_item_by_serial(serial)

def normalize_item_text(text):
    """
    Удаляет из текста товара серийный номер и пометки о брони,
    оставляя только описание модели для группировки.
    """
    # Удаляем серийный номер (если он есть)
    serial = extract_serial(text)
    if serial:
        text = re.sub(rf'\s*\({re.escape(serial)}\)', '', text)
    # Удаляем пометки о брони вида (Бронь от ...)
    text = re.sub(r'\s*\(Бронь от \d{2}\.\d{2}\)', '', text, flags=re.IGNORECASE)
    return text.strip()
