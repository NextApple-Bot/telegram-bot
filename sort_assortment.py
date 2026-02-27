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
    """
    Разбирает текст на категории.
    Категориями считаются:
      - однострочные заголовки, начинающиеся и заканчивающиеся дефисами, содержащие двоеточие.
      - трёхстрочные заголовки (строка дефисов, строка с двоеточием, строка дефисов).
    Все остальные строки с двоеточием (например, '128GB:', '-SIM+eSIM-') игнорируются.
    Разделительные строки из дефисов пропускаются.
    Всё остальное считается товарами текущей категории.
    """
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

        # Проверка на однострочный заголовок (дефисы вокруг, есть двоеточие)
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

        # Проверка на трёхстрочный заголовок
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

        # Игнорируем подзаголовки типа -SIM+eSIM-, -eSIM-
        if re.match(r'^-\s*[^-]+\s*-$', trimmed):
            i += 1
            continue

        # Игнорируем любые другие строки, оканчивающиеся двоеточием (например, '128GB:')
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

def sort_items_in_category(items, header):
    header_lower = header.lower()
    output = []

    if 'iphone' in header_lower:
        groups = {}
        for item in items:
            sim = detect_sim_type(item)
            match = re.search(r'(\d+)\s*(gb|tb)', item, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                unit = match.group(2).lower()
                vol_gb = num * 1024 if unit == 'tb' else num
                vol_str = f"{num}{unit.upper()}"
            else:
                vol_gb = None
                vol_str = None
            key = (vol_gb, vol_str)
            if key not in groups:
                groups[key] = {'eSIM': [], 'SIM+eSIM': [], 'other': []}
            groups[key][sim].append(item)

        sorted_keys = sorted(groups.keys(), key=lambda k: (k[0] is None, k[0] if k[0] is not None else float('inf')))
        for vol_gb, vol_str in sorted_keys:
            if vol_str is not None:
                output.append(f"{vol_str}:")
                output.append('-')
            for sim_type in ['eSIM', 'SIM+eSIM', 'other']:
                items_list = groups[(vol_gb, vol_str)][sim_type]
                if items_list:
                    if sim_type != 'other':
                        output.append(f'-{sim_type}-')
                        output.append('-')
                    output.extend(sorted(items_list))
                    output.append('-')
        return output

    elif 'apple watch' in header_lower:
        size_groups = {}
        for item in items:
            size = extract_watch_size(item)
            size_groups.setdefault(size, []).append(item)
        sorted_sizes = sorted(size_groups.keys(), key=lambda s: (s is None, s if s is not None else float('inf')))
        for size in sorted_sizes:
            if size is not None:
                output.append(f"{size}mm:")
                output.append('-')
                output.extend(sorted(size_groups[size]))
                output.append('-')
        return output

    else:
        return sorted(items)

def sort_assortment_to_categories(input_text):
    lines = input_text.splitlines()
    return parse_categories(lines)

def build_output_text(categories):
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

        sorted_output = sort_items_in_category(cat['items'], header)
        if isinstance(sorted_output, list):
            output_lines.extend(sorted_output)
        else:
            output_lines.append(sorted_output)

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
