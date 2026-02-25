import re

# Порядок поколений процессоров Mac
MAC_GENERATIONS = ["M1", "M2", "M3", "M4", "M5", "M6"]

def extract_mac_gen(item):
    """Извлекает поколение процессора Mac (M1, M2 и т.д.) из строки товара."""
    match = re.search(r'\b(M\d+)\b', item, re.IGNORECASE)
    if match:
        gen = match.group(1).upper()
        return gen
    return None

def mac_gen_order(gen):
    """Возвращает индекс поколения для сортировки."""
    try:
        return MAC_GENERATIONS.index(gen)
    except ValueError:
        return len(MAC_GENERATIONS)  # неизвестные поколения в конец

def detect_sim_type(item):
    lower = item.lower()
    if 'sim+esim' in lower or '(sim+esim)' in lower:
        return 'SIM+eSIM'
    elif 'esim' in lower or '(esim)' in lower:
        return 'eSIM'
    else:
        return 'other'

def extract_volume_info(item):
    match = re.search(r'(\d+)\s*(gb|tb)', item, re.IGNORECASE)
    if not match:
        return None, None
    num = int(match.group(1))
    unit = match.group(2).lower()
    if unit == 'tb':
        volume_gb = num * 1024
        volume_str = f"{num}TB"
    else:
        volume_gb = num
        volume_str = f"{num}GB"
    return volume_gb, volume_str

def extract_watch_size(item):
    match = re.search(r'(\d+)\s*mm', item, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def category_type(header):
    lower = header.lower()
    if 'iphone' in lower:
        return 'iphone'
    if 'apple watch' in lower:
        return 'watch'
    if 'macbook' in lower or 'macbook air' in lower or 'macbook pro' in lower:
        return 'macbook'
    return 'other'

def sort_items_in_category(items, cat_type):
    if cat_type == 'iphone':
        # Группировка по объёму, внутри по SIM
        volume_groups = {}
        for item in items:
            vol_gb, vol_str = extract_volume_info(item)
            sim = detect_sim_type(item)
            key = (vol_gb, vol_str)
            if key not in volume_groups:
                volume_groups[key] = {'eSIM': [], 'SIM+eSIM': [], 'other': []}
            volume_groups[key][sim].append(item)

        sorted_keys = sorted(volume_groups.keys(), key=lambda k: (k[0] is None, k[0] if k[0] is not None else float('inf')))
        output = []
        for (vol_gb, vol_str), sim_dict in sorted_keys:
            if vol_gb is not None:
                output.append(f"{vol_str}:")
                output.append('-')
            for sim_type in ['eSIM', 'SIM+eSIM', 'other']:
                items_list = sim_dict[sim_type]
                if items_list:
                    output.append(f'-{sim_type}-')
                    output.append('-')
                    output.extend(sorted(items_list))
                    output.append('-')
        return output

    elif cat_type == 'watch':
        # Группировка по размеру
        size_groups = {}
        for item in items:
            size = extract_watch_size(item)
            size_groups.setdefault(size, []).append(item)
        sorted_sizes = sorted(size_groups.keys(), key=lambda s: (s is None, s if s is not None else float('inf')))
        output = []
        for size in sorted_sizes:
            if size is not None:
                output.append(f"{size}mm:")
                output.append('-')
                output.extend(sorted(size_groups[size]))
                output.append('-')
        return output

    elif cat_type == 'macbook':
        # Группировка по поколению процессора, внутри по объёму
        gen_groups = {}
        for item in items:
            gen = extract_mac_gen(item)
            if gen is None:
                gen = "Other"
            vol_gb, vol_str = extract_volume_info(item)
            gen_groups.setdefault(gen, []).append((vol_gb, vol_str, item))

        sorted_gens = sorted(gen_groups.keys(), key=lambda g: (mac_gen_order(g) if g != "Other" else float('inf')))

        output = []
        for gen in sorted_gens:
            items_with_vol = gen_groups[gen]
            items_with_vol.sort(key=lambda x: (x[0] is None, x[0] if x[0] is not None else float('inf'), x[2]))
            output.append(f"{gen}:")
            output.append('-')
            # Группировка по объёму внутри поколения
            vol_groups = {}
            for (vol_gb, vol_str, item) in items_with_vol:
                key = vol_gb if vol_gb is not None else "no_vol"
                vol_groups.setdefault(key, []).append(item)
            sorted_vol_keys = sorted(vol_groups.keys(), key=lambda k: (k == "no_vol", k if k != "no_vol" else float('inf')))
            for vol_key in sorted_vol_keys:
                if vol_key != "no_vol":
                    _, vol_str, _ = next((v for v in items_with_vol if v[0] == vol_key), (None, None, None))
                    output.append(f"{vol_str}:")
                    output.append('-')
                output.extend(sorted(vol_groups[vol_key]))
                output.append('-')
        return output

    else:  # other – просто сортировка по алфавиту
        return sorted(items)

def parse_categories(lines):
    categories = []
    current_header = None
    current_items = []
    for line in lines:
        stripped = line.rstrip('\n')
        trimmed = stripped.strip()
        if trimmed == '':
            continue
        if re.match(r'^\s*-+\s*$', stripped):
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

def build_output_text(categories):
    output_lines = []
    for cat in categories:
        header = cat['header']
        dash_len = len(header) + 2
        output_lines.append('-' * dash_len)
        output_lines.append(header)
        output_lines.append('-' * dash_len)
        output_lines.append('-')

        cat_type = category_type(header)
        sorted_items = sort_items_in_category(cat['items'], cat_type)
        output_lines.extend(sorted_items)

        output_lines.append('')
    return '\n'.join(output_lines)

def sort_assortment_to_categories(input_text):
    lines = input_text.splitlines()
    return parse_categories(lines)

def extract_model_and_volume(text):
    lower = text.lower()
    match = re.search(r'(iphone\s[\d\w\s]+?)(?:\d+gb|\d+tb)', lower)
    if match:
        model = match.group(1).strip()
    else:
        if ',' in text:
            model = text.split(',')[0].strip()
        else:
            model = text
    volume_match = re.search(r'(\d+\s*(?:gb|tb))', lower, re.IGNORECASE)
    volume = volume_match.group(1).upper().replace(' ', '') if volume_match else ''
    return model, volume

def find_category_for_item(item, categories):
    lower_item = item.lower()
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
    for idx, cat in enumerate(categories):
        header_clean = cat['header'].rstrip(':').strip()
        if header_clean and header_clean.lower() in lower_item:
            return idx
    return None

def add_item_to_categories(item, categories):
    idx = find_category_for_item(item, categories)
    if idx is not None:
        categories[idx]['items'].append(item)
        return categories, idx
    else:
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