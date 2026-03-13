import re

def normalize_name(name):
    return ' '.join(name.split())

def normalize_model(name):
    return re.sub(r'S\s+(\d+)', r'S\1', name, flags=re.IGNORECASE)

def extract_memory(text):
    match = re.search(r'(\d+)\s*(gb|гб|tb)', text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"
    return None

def extract_watch_size(text):
    match = re.search(r'(\d+)\s*mm', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def detect_sim_type(text):
    lower = text.lower()
    if re.search(r'\(sim\+esim\)|\bsim\+esim\b', lower):
        return 'SIM+eSIM'
    if re.search(r'\(esim\)|\besim\b', lower):
        return 'eSIM'
    return 'other'

def get_full_model_name(item):
    """
    Возвращает полное название товара без серийных номеров и пометок в скобках,
    но с сохранением цвета, памяти и других характеристик.
    Используется для группировки остатков.
    """
    # Удаляем всё содержимое круглых скобок
    without_brackets = re.sub(r'\([^)]*\)', '', item)
    # Нормализуем пробелы
    return normalize_name(without_brackets)

def extract_base_name(item):
    """
    Возвращает базовое имя товара (модель + память) для определения категории.
    Удаляет цвет и другие детали, оставляя только основу.
    """
    # Удаляем всё в скобках
    without_brackets = re.sub(r'\([^)]*\)', '', item)
    # Разделяем по запятой, берём первую часть (модель и цвет, если нет запятой)
    if ',' in without_brackets:
        model_part = without_brackets.split(',', 1)[0].strip()
    else:
        model_part = without_brackets.strip()
    # Добавляем память, если она есть в исходной строке
    memory = extract_memory(without_brackets)
    if memory:
        base = f"{model_part} {memory}"
    else:
        base = model_part
    # Нормализуем
    base = normalize_name(base)
    base = normalize_model(base)
    return base

# ... остальные функции без изменений (parse_categories, _add_category, sort_assortment_to_categories и т.д.)
# Они остаются такими же, как в предыдущей версии.
