import json
import os
import re
import shutil
from datetime import datetime
from config import INVENTORY_FILE, BACKUP_DIR, MAX_BACKUPS

UNIT_PATTERN = re.compile(r'^\d+\s*(mm|см|дюйм|gb|tb|mb|р|руб|\$|€|%|скидка|бонус)$', re.IGNORECASE)
TELEPHONE_PATTERN = re.compile(r'^\+?\d{10,12}$')

def is_likely_serial(token, in_brackets=False):
    """
    Проверяет, похож ли токен на серийный номер.
    Если токен содержит символ '№', считаем его серийным (длина >=2).
    Иначе применяем стандартные правила.
    """
    # Если есть символ №, считаем серийным, если длина >=2
    if '№' in token:
        return len(token) >= 2

    # Проверка на допустимые символы
    if not re.match(r'^[A-Za-z0-9\-._]+$', token):
        return False
    if len(token) < 5:
        return False
    if TELEPHONE_PATTERN.match(token):
        return False
    if UNIT_PATTERN.match(token):
        return False
    if token.isdigit():
        return True
    if re.search(r'\d', token) and re.search(r'[A-Z]', token):
        return True
    if token.isupper() and len(token) >= 8:
        return True
    return False

def extract_serial(line):
    """
    Извлекает серийный номер из строки товара.
    Ищет содержимое в круглых скобках, которое:
    - состоит из латинских букв, цифр, дефисов;
    - длина не менее 5 символов;
    - содержит хотя бы одну букву и одну цифру, либо является длинным числом (≥10 цифр).
    Возвращает нормализованный серийный номер (в верхнем регистре) или None.
    """
    # Ищем все вхождения в скобках, где внутри только допустимые символы
    matches = re.finditer(r'\(([A-Za-z0-9\-]{5,})\)', line)
    for match in matches:
        candidate = match.group(1)
        # Проверяем, что есть и буква, и цифра (типичный серийник)
        if re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            return candidate.upper()
        # Если это длинное число (например, IMEI) – тоже считаем серийным
        if candidate.isdigit() and len(candidate) >= 10:
            return candidate
    # Если ничего не подошло
    return None

def load_inventory():
    if not os.path.exists(INVENTORY_FILE):
        return []
    with open(INVENTORY_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
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
