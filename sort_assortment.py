import re

# --- Нормализация и вспомогательные функции ---

def normalize_name(name):
    """Убирает лишние пробелы в начале/конце и множественные пробелы внутри."""
    return ' '.join(name.split())

def normalize_model(name):
    """Для Apple Watch убирает пробел после S: 'S 11' -> 'S11'."""
    return re.sub(r'S\s+(\d+)', r'S\1', name, flags=re.IGNORECASE)

def extract_memory(text):
    """Извлекает объём памяти (число перед GB/гб/TB)."""
    match = re.search(r'(\d+)\s*(gb|гб|tb)', text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"
    return None

def extract_watch_size(text):
    """Извлекает размер часов в мм."""
    match = re.search(r'(\d+)\s*mm', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def extract_mac_gen(text):
    """Извлекает поколение процессора Mac (M1, M2, ...)."""
    match = re.search(r'\b(M\d+)\b', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None

def detect_sim_type(text):
    """Определяет тип SIM: 'eSIM', 'SIM+eSIM' или 'other'."""
    lower = text.lower()
    if re.search(r'\(sim\+esim\)|\bsim\+esim\b', lower):
        return 'SIM+eSIM'
    if re.search(r'\(esim\)|\besim\b', lower):
        return 'eSIM'
    return 'other'

def extract_base_name(item):
    """
    Извлекает базовое имя товара (модель + память) для поиска категории.
    Для iPhone: часть до запятой + память.
    """
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

# --- Парсинг категорий из текста ---

def parse_categories(lines):
    """
    Разбирает текст на категории. Строка, оканчивающаяся на ':', считается заголовком.
    Возвращает список словарей: [{"header": строка, "items": [строки товаров]}, ...]
    """
    categories = []
    current_header = None
    current_items = []

    for line in lines:
        stripped = line.rstrip('\n')
        trimmed = stripped.strip()
        if trimmed == '':
            continue
        # Пропускаем строки, состоящие только из дефисов (заголовки мы не пропускаем, они обрабатываются отдельно)
        if re.match(r'^\s*-+\s*$', stripped) and not trimmed.endswith(':'):
            continue
        if trimmed.endswith(':'):
            if current_header is not None and current_items:
                categories.append({"header": current_header, "items": current_items})
                current_items = []
            current_header = normalize_name(trimmed)
        else:
            if current_header is None:
                current_header = "Общее:"
            current_items.append(stripped)

    if current_header is not None and current_items:
        categories.append({"header": current_header, "items": current_items})
    return categories

# --- Сортировка товаров внутри категории ---

def sort_items_in_category(items, header):
    """
    Возвращает список строк для вставки в выходной текст.
    Включает подзаголовки (-eSIM-, -SIM+eSIM-), группировку по памяти и разделители.
    """
    header_lower = header.lower()
    output = []

    # Определяем тип категории для специальной обработки
    if 'iphone' in header_lower:
        # Группировка по объёму памяти, внутри по SIM
        groups = {}  # (vol_gb, vol_str) -> {'eSIM': [], 'SIM+eSIM': [], 'other': []}
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

        # Сортируем ключи: None в конце, остальные по возрастанию объёма
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
        # Группировка по размеру
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

    elif 'macbook' in header_lower:
        # Группировка по поколению процессора, внутри по объёму
        mac_generations = ["M1", "M2", "M3", "M4", "M5", "M6"]
        gen_groups = {}
        for item in items:
            gen = extract_mac_gen(item)
            if gen is None:
                gen = "Other"
            vol_gb, vol_str = extract_memory(item)  # vol_str уже сформирован
            # Преобразуем vol_str в объём для сортировки
            if vol_str:
                num = int(re.search(r'\d+', vol_str).group())
                unit = vol_str[-2:].lower()
                vol_gb = num * 1024 if unit == 'tb' else num
            else:
                vol_gb = None
            gen_groups.setdefault(gen, []).append((vol_gb, vol_str, item))

        # Сортируем поколения по порядку
        def gen_key(g):
            if g == "Other":
                return float('inf')
            try:
                return mac_generations.index(g)
            except ValueError:
                return len(mac_generations) + 1
        sorted_gens = sorted(gen_groups.keys(), key=gen_key)

        for gen in sorted_gens:
            items_with_vol = gen_groups[gen]
            # Сортируем внутри поколения по объёму
            items_with_vol.sort(key=lambda x: (x[0] is None, x[0] if x[0] is not None else float('inf'), x[2]))
            output.append(f"{gen}:")
            output.append('-')
            # Группировка по объёму
            vol_groups = {}
            for (vol_gb, vol_str, item) in items_with_vol:
                key = vol_gb if vol_gb is not None else "no_vol"
                vol_groups.setdefault(key, []).append(item)
            sorted_vol_keys = sorted(vol_groups.keys(), key=lambda k: (k == "no_vol", k if k != "no_vol" else float('inf')))
            for vol_key in sorted_vol_keys:
                if vol_key != "no_vol":
                    # Найдём любой товар с таким объёмом, чтобы получить vol_str
                    vol_str = next((v for v in items_with_vol if v[0] == vol_key), (None, None, None))[1]
                    output.append(f"{vol_str}:")
                    output.append('-')
                output.extend(sorted(vol_groups[vol_key]))
                output.append('-')
        return output

    else:
        # Остальные категории: просто сортируем по алфавиту
        return sorted(items)

# --- Основные функции для бота ---

def sort_assortment_to_categories(input_text):
    """Принимает текст файла, возвращает список категорий (без сортировки внутри)."""
    lines = input_text.splitlines()
    return parse_categories(lines)

def build_output_text(categories):
    """Принимает список категорий, возвращает отформатированный текст с сортировкой."""
    output_lines = []
    for cat in categories:
        header = cat['header']
        # Нормализуем заголовок для вывода (но сохраняем оригинальный формат с двоеточием)
        display_header = normalize_name(header)
        if not display_header.endswith(':'):
            display_header += ':'
        dash_len = len(display_header) + 2
        output_lines.append('-' * dash_len)
        output_lines.append(display_header)
        output_lines.append('-' * dash_len)
        output_lines.append('-')

        # Сортируем товары внутри категории
        sorted_output = sort_items_in_category(cat['items'], header)
        if isinstance(sorted_output, list):
            output_lines.extend(sorted_output)
        else:
            output_lines.append(sorted_output)  # если вдруг строка

        output_lines.append('')
    return '\n'.join(output_lines)

def find_category_for_item(item, categories):
    """
    Находит индекс категории, в которую должен попасть товар.
    Для iPhone ищет по модели + память, для остальных – по вхождению имени категории.
    Возвращает индекс или None.
    """
    normalized_item = normalize_name(item)
    normalized_item = normalize_model(normalized_item).lower()
    base = extract_base_name(item).lower()

    # Сначала ищем точное совпадение базового имени с заголовком
    for idx, cat in enumerate(categories):
        cat_name = normalize_name(cat['header']).lower()
        if cat_name.endswith(':'):
            cat_name = cat_name[:-1].strip()
        if cat_name == base:
            return idx

    # Затем ищем вхождение
    for idx, cat in enumerate(categories):
        cat_name = normalize_name(cat['header']).lower()
        if cat_name.endswith(':'):
            cat_name = cat_name[:-1].strip()
        if cat_name and (cat_name in base or base in cat_name):
            return idx

    return None

def add_item_to_categories(item, categories):
    """
    Добавляет товар в подходящую категорию.
    Если категория не найдена, создаёт новую.
    Возвращает (обновлённый список, индекс категории).
    """
    idx = find_category_for_item(item, categories)
    if idx is not None:
        categories[idx]['items'].append(item)
        return categories, idx
    else:
        # Создаём новую категорию
        if 'iphone' in item.lower():
            # Пытаемся выделить модель и память
            base = extract_base_name(item)
            new_header = f"{base}:"
        else:
            # Для остальных используем первое слово до запятой или всё, что есть
            if ',' in item:
                new_header = item.split(',')[0].strip() + ':'
            else:
                # Если нет запятой, берём первые два слова
                words = item.split()[:2]
                new_header = ' '.join(words).strip() + ':'
        new_header = normalize_name(new_header)
        categories.append({"header": new_header, "items": [item]})
        return categories, len(categories)-1
