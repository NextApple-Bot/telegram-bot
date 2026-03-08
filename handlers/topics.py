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

def extract_base_name(item):
    if ',' in item:
        model_part = item.split(',', 1)[0].strip()
    else:
        model_part = item.strip()
    memory = extract_memory(item)
    if memory:
        base = f"{model_part} {memory}"
    else:
        base = model_part
    base = normalize_name(base)
    base = normalize_model(base)
    return base

def parse_categories(lines):
    categories = []
    current_header = None
    current_items = []
    i = 0
    n = len(lines)

    while i < n:
        stripped = lines[i].rstrip('\n')
        trimmed = stripped.strip()
        if trimmed == '':
            i += 1
            continue

        # Однострочный заголовок (дефисы вокруг, есть двоеточие)
        if trimmed.startswith('-') and trimmed.endswith('-') and ':' in trimmed:
            if current_header is not None and current_items:
                categories.append({"header": current_header, "items": current_items})
                current_items = []
            header_text = trimmed.strip('- ').strip()
            if header_text.endswith(':'):
                header_text = header_text[:-1].strip()
            current_header = normalize_name(header_text)
            i += 1
            continue

        # Трёхстрочный заголовок
        if (re.match(r'^\s*-+\s*$', stripped) and
            i + 1 < n and ':' in lines[i + 1] and
            i + 2 < n and re.match(r'^\s*-+\s*$', lines[i + 2])):
            header_line = lines[i + 1].strip()
            header_text = header_line.strip('- ').strip()
            if header_text.endswith(':'):
                header_text = header_text[:-1].strip()
            if current_header is not None and current_items:
                categories.append({"header": current_header, "items": current_items})
                current_items = []
            current_header = normalize_name(header_text)
            i += 3
            continue

        # Пропускаем строки, состоящие только из дефисов (разделители)
        if re.match(r'^\s*-+\s*$', stripped):
            i += 1
            continue

        # Игнорируем подзаголовки типа -SIM+eSIM- и -eSIM-
        if re.match(r'^-\s*[^-]+\s*-$', trimmed):
            i += 1
            continue

        # Игнорируем любые строки, оканчивающиеся двоеточием (например, '128GB:', '49mm:')
        if trimmed.endswith(':'):
            i += 1
            continue

        # Всё остальное считаем товаром
        if current_header is None:
            current_header = "Общее:"
        current_items.append(stripped)
        i += 1

    if current_header is not None and current_items:
        categories.append({"header": current_header, "items": current_items})
    return categories

def build_output_text(categories):
    """Формирует текст для вывода, сохраняя исходный порядок товаров в категориях."""
    output_lines = []
    for cat in categories:
        header = cat['header']
        display_header = normalize_name(header)
        if not display_header.endswith(':'):
            display_header += ':'
        dash_len = len(display_header) + 2
        output_lines.append('-' * dash_len)
        output_lines.append(display_header)
        output_lines.append('-' * dash_len)
        output_lines.append('-')

        # ВАЖНО: выводим товары в том порядке, в котором они были загружены
        # БЕЗ какой-либо сортировки
        for item in cat['items']:
            output_lines.append(item)

        output_lines.append('')
    return '\n'.join(output_lines)

def find_category_for_item(item, categories):
    normalized_item = normalize_name(item)
    normalized_item = normalize_model(normalized_item).lower()
    base = extract_base_name(item).lower()

    for idx, cat in enumerate(categories):
        cat_name = normalize_name(cat['header']).lower()
        if cat_name.endswith(':'):
            cat_name = cat_name[:-1].strip()
        if cat_name == base:
            return idx

    for idx, cat in enumerate(categories):
        cat_name = normalize_name(cat['header']).lower()
        if cat_name.endswith(':'):
            cat_name = cat_name[:-1].strip()
        if cat_name and (cat_name in base or base in cat_name):
            return idx

    return None

def add_item_to_categories(item, categories):
    # Специальная обработка для Б/У
    if item.strip().startswith("Б/У -") or item.strip().startswith("Б/У "):
        for idx, cat in enumerate(categories):
            cat_name = normalize_name(cat['header']).lower()
            if cat_name == "б/у" or cat_name == "б/у:":
                categories[idx]['items'].append(item)
                return categories, idx
        new_cat = {"header": "Б/У:", "items": [item]}
        categories.append(new_cat)
        return categories, len(categories)-1

    idx = find_category_for_item(item, categories)
    if idx is not None:
        categories[idx]['items'].append(item)
        return categories, idx
    else:
        if 'iphone' in item.lower():
            base = extract_base_name(item)
            new_header = f"{base}:"
        else:
            if ',' in item:
                new_header = item.split(',')[0].strip() + ':'
            else:
                words = item.split()[:2]
                new_header = ' '.join(words).strip() + ':'
        new_header = normalize_name(new_header)
        categories.append({"header": new_header, "items": [item]})
        return categories, len(categories)-1
