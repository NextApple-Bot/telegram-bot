import re
from database import (
    add_item, remove_item_by_serial, get_items_grouped_by_category,
    get_or_create_category, get_item_id_by_serial
)

UNIT_PATTERN = re.compile(r'^\d+\s*(mm|см|дюйм|gb|tb|mb|р|руб|\$|€|%|скидка|бонус)$', re.IGNORECASE)
TELEPHONE_PATTERN = re.compile(r'^\+?\d{10,11}$')

def extract_serial(line):
    """Извлекает серийный номер из строки товара (как и раньше)."""
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
    Полностью заменяет ассортимент новыми категориями (используется при загрузке из файла).
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
    return await remove_item_by_serial(serial)        new_data = [{"header": "Общее:", "items": items}]
        backup_current()
        save_inventory(new_data)
        return new_data
    return data

def backup_current():
    if not os.path.exists(INVENTORY_FILE):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"inventory_backup_{timestamp}.json"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    shutil.copy2(INVENTORY_FILE, backup_path)
    clean_old_backups()

def clean_old_backups():
    if not os.path.exists(BACKUP_DIR):
        return
    backups = [f for f in os.listdir(BACKUP_DIR) if f.startswith("inventory_backup_") and f.endswith(".json")]
    backups.sort(reverse=True)
    if len(backups) > MAX_BACKUPS:
        for old in backups[MAX_BACKUPS:]:
            os.remove(os.path.join(BACKUP_DIR, old))

def save_inventory(inventory):
    backup_current()
    with open(INVENTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2)

def remove_by_serial(inventory, serial):
    removed_total = 0
    new_inventory = []
    for category in inventory:
        new_items = [item for item in category['items'] if extract_serial(item) != serial]
        removed = len(category['items']) - len(new_items)
        if removed > 0:
            removed_total += removed
        new_inventory.append({'header': category['header'], 'items': new_items})
    return new_inventory, removed_total

def text_only(inventory):
    items = []
    for cat in inventory:
        items.extend(cat['items'])
    return items

def parse_lines_to_objects(lines):
    objects = []
    for line in lines:
        serial = extract_serial(line)
        objects.append({"text": line, "serial": serial})
    return objects

def extract_serials_from_text(text):
    """Извлекает все серийные номера из текста сообщения (только в скобках)."""
    serials = set()
    matches = re.finditer(r'\(([A-Za-z0-9\-]{5,})\)', text)
    for match in matches:
        candidate = match.group(1)
        if re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            serials.add(candidate.upper())
        elif candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
    return list(serials)
