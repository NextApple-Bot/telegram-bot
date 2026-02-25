import re

# Список моделей iPhone для порядка сортировки категорий (можно дополнять)
IPHONE_MODEL_ORDER = [
    "iPhone 13",
    "iPhone 14",
    "iPhone 15",
    "iPhone 16",
    "iPhone 17",
    "iPhone 13 Pro",
    "iPhone 14 Pro",
    "iPhone 15 Pro",
    "iPhone 16 Pro",
    "iPhone 17 Pro",
    "iPhone 13 Pro Max",
    "iPhone 14 Pro Max",
    "iPhone 15 Pro Max",
    "iPhone 16 Pro Max",
    "iPhone 17 Pro Max",
    "iPhone Air",
    "iPhone 16e",
]

def is_iphone_category(header):
    """Проверяет, относится ли категория к iPhone."""
    return "iphone" in header.lower()

def detect_sim_type(item):
    """Определяет тип SIM из строки товара."""
    lower = item.lower()
    if 'sim+esim' in lower or '(sim+esim)' in lower:
        return 'SIM+eSIM'
    elif 'esim' in lower or '(esim)' in lower:
        return 'eSIM'
    else:
        return 'other'

def parse_categories(lines):
    """
    Разбирает текст на категории, сохраняя заголовки и товары.
    Возвращает список словарей [{"header": header, "items": [item1, item2, ...]}].
    """
    categories = []
    current_header = None
    current_items = []

    for line in lines:
        stripped = line.rstrip('\n')
        trimmed = stripped.strip()
        if trimmed == '':
            continue
        if re.match(r'^\s*-+\s*$', stripped):  # разделители из дефисов
            continue
        if stripped.endswith(':'):
            if current_header is not None:
                categories.append({"header": current_header, "items": current_items})
                current_items = []
            current_header = stripped
        else:
            if current_header is None:
                current_header = "Общее:"
            current_items.append(stripped)

    if current_header is not None:
        categories.append({"header": current_header, "items": current_items})
    return categories

def sort_items_in_category(items, is_iphone):
    """
    Сортирует товары внутри категории.
    Если is_iphone == True: группирует по типу SIM, внутри групп сортирует по алфавиту.
    Иначе: просто сортирует по алфавиту (можно изменить на items, если нужен исходный порядок).
    """
    if is_iphone:
        groups = {'eSIM': [], 'SIM+eSIM': [], 'other': []}
        for item in items:
            sim = detect_sim_type(item)
            groups[sim].append(item)
        for g in groups:
            groups[g].sort()
        result = []
        if groups['eSIM']:
            result.append('-eSIM-')
            result.append('-')
            result.extend(groups['eSIM'])
            result.append('-')
        if groups['SIM+eSIM']:
            result.append('-SIM+eSIM-')
            result.append('-')
            result.extend(groups['SIM+eSIM'])
            result.append('-')
        if groups['other']:
            result.extend(groups['other'])
            result.append('-')
        return result
    else:
        # Для не-iPhone категорий – сортировка по алфавиту
        return sorted(items)

def build_output_text(categories):
    """
    Строит текст для вывода с заголовками и разделителями.
    Для iPhone-категорий применяет группировку по SIM.
    """
    output_lines = []
    for cat in categories:
        header = cat['header']
        dash_len = len(header) + 2
        output_lines.append('-' * dash_len)
        output_lines.append(header)
        output_lines.append('-' * dash_len)
        output_lines.append('-')

        is_iphone = is_iphone_category(header)
        sorted_items = sort_items_in_category(cat['items'], is_iphone)
        output_lines.extend(sorted_items)

        output_lines.append('')  # пустая строка между категориями
    return '\n'.join(output_lines)

def sort_assortment_to_categories(input_text):
    """
    Принимает сырой текст ассортимента, возвращает категории с отсортированными товарами
    (сохраняя исходные заголовки).
    """
    lines = input_text.splitlines()
    return parse_categories(lines)

def extract_model_and_volume(text):
    """Извлекает модель и объём из строки товара для iPhone."""
    lower = text.lower()
    # Ищем шаблон типа "iphone 17 pro max"
    match = re.search(r'(iphone\s[\d\w\s]+?)(?:\d+gb|\d+tb)', lower)
    if match:
        model = match.group(1).strip()
    else:
        # Пробуем взять часть до запятой, если есть запятая
        if ',' in text:
            model = text.split(',')[0].strip()
        else:
            model = text
    # Ищем объём
    volume_match = re.search(r'(\d+\s*(?:gb|tb))', lower, re.IGNORECASE)
    volume = volume_match.group(1).upper().replace(' ', '') if volume_match else ''
    return model, volume

def find_category_for_item(item, categories):
    """
    Определяет индекс категории, в которую следует поместить товар.
    Для iPhone – точное совпадение модели и объёма.
    Для остальных – поиск по ключевому слову (заголовок категории без двоеточия).
    Возвращает индекс или None.
    """
    lower_item = item.lower()

    # Если товар содержит "iphone", используем специальную логику
    if 'iphone' in lower_item:
        model, volume = extract_model_and_volume(item)
        if volume:
            target_header = f"{model} {volume}:".strip()
        else:
            target_header = f"{model}:".strip()
        for idx, cat in enumerate(categories):
            if cat['header'].strip().lower() == target_header.lower():
                return idx
        return None

    # Для остальных товаров – ищем категорию, чей заголовок (без двоеточия) содержится в тексте товара
    for idx, cat in enumerate(categories):
        header_clean = cat['header'].rstrip(':').strip()
        if header_clean and header_clean.lower() in lower_item:
            return idx
    return None

def add_item_to_categories(item, categories):
    """Добавляет товар в существующую категорию или создаёт новую."""
    idx = find_category_for_item(item, categories)
    if idx is not None:
        categories[idx]['items'].append(item)
        return categories, idx
    else:
        # Если не найдено, создаём новую категорию. Для iPhone – по модели и объёму, иначе – "Общее:"
        if 'iphone' in item.lower():
            model, volume = extract_model_and_volume(item)
            if volume:
                new_header = f"{model} {volume}:".strip()
            else:
                new_header = f"{model}:".strip()
        else:
            new_header = "Общее:"
        categories.append({"header": new_header, "items": [item]})
        return categories, len(categories)-1