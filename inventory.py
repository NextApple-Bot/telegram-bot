import json
import os
import re
import shutil
from datetime import datetime
from config import INVENTORY_FILE, BACKUP_DIR, MAX_BACKUPS

# Регулярные выражения для отсеивания ложных срабатываний
UNIT_PATTERN = re.compile(r'^\d+\s*(mm|см|дюйм|gb|tb|mb|р|руб|\$|€|%|скидка|бонус)$', re.IGNORECASE)
TELEPHONE_PATTERN = re.compile(r'^\+?\d{10,11}$')

def is_likely_serial(token, in_brackets=False):
    if in_brackets:
        return True
    if len(token) < 6:
        return False
    if TELEPHONE_PATTERN.match(token):
        return False
    if token.isdigit():
        return True
    if UNIT_PATTERN.match(token):
        return False
    if re.search(r'\d', token):
        return True
    if token.isupper() and len(token) >= 8:
        return True
    return False

def extract_serial(line):
    match = re.search(r'\(([A-Za-zА-Яа-я0-9\-._]{4,})\)', line)
    if match:
        token = match.group(1)
        if is_likely_serial(token, in_brackets=True):
            return token
    tokens = re.findall(r'\b([A-Za-zА-Яа-я0-9\-._]{4,})\b', line)
    for token in tokens:
        if is_likely_serial(token, in_brackets=False):
            return token
    return None

def load_inventory():
    if not os.path.exists(INVENTORY_FILE):
        return []
    with open(INVENTORY_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Миграция старого формата (плоский список)
    if isinstance(data, list) and all(isinstance(item, dict) and "text" in item for item in data):
        items = [item["text"] for item in data]
        new_data = [{"header": "Общее:", "items": items}]
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
    serials = set()
    for match in re.finditer(r'\(([A-Za-zА-Яа-я0-9\-._]{4,})\)', text):
        token = match.group(1)
        if is_likely_serial(token, in_brackets=True):
            serials.add(token)
    for match in re.finditer(r'\b([A-Za-zА-Яа-я0-9\-._]{4,})\b', text):
        token = match.group(1)
        if token in serials:
            continue
        if is_likely_serial(token, in_brackets=False):
            serials.add(token)
    return list(serials)