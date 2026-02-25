import re

def detect_sim_type(text):
    lower = text.lower()
    if 'sim+esim' in lower or '(sim+esim)' in lower:
        return 'SIM+eSIM'
    elif 'esim' in lower or '(esim)' in lower:
        return 'eSIM'
    else:
        return None

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
        if re.match(r'^-esim-$', trimmed, re.IGNORECASE) or re.match(r'^-sim\+esim-$', trimmed, re.IGNORECASE):
            continue
        if stripped.endswith(':'):
            if current_header is not None and current_items:
                categories.append({'header': current_header, 'items': current_items})
                current_items = []
            current_header = stripped
        else:
            if current_header is None:
                current_header = "Общее:"
            current_items.append(stripped)
    if current_header is not None and current_items:
        categories.append({'header': current_header, 'items': current_items})
    return categories

def group_items(items):
    groups = {'eSIM': [], 'SIM+eSIM': [], 'other': []}
    for item in items:
        sim_type = detect_sim_type(item)
        if sim_type:
            groups[sim_type].append(item)
        else:
            groups['other'].append(item)
    for key in groups:
        groups[key].sort()
    return groups

def build_output_text(categories):
    output_lines = []
    for cat in categories:
        header = cat['header']
        dash_len = len(header) + 2
        output_lines.append('-' * dash_len)
        output_lines.append(header)
        output_lines.append('-' * dash_len)
        output_lines.append('-')
        grouped = group_items(cat['items'])
        if grouped['eSIM']:
            output_lines.append('-eSIM-')
            output_lines.append('-')
            output_lines.extend(grouped['eSIM'])
            output_lines.append('-')
        if grouped['SIM+eSIM']:
            output_lines.append('-SIM+eSIM-')
            output_lines.append('-')
            output_lines.extend(grouped['SIM+eSIM'])
            output_lines.append('-')
        if grouped['other']:
            output_lines.extend(grouped['other'])
            output_lines.append('-')
        output_lines.append('')
    return '\n'.join(output_lines)

def sort_assortment_to_categories(input_text):
    lines = input_text.splitlines()
    raw_cats = parse_categories(lines)
    for cat in raw_cats:
        grouped = group_items(cat['items'])
        new_items = []
        for grp in ['eSIM', 'SIM+eSIM']:
            new_items.extend(grouped[grp])
        new_items.extend(grouped['other'])
        cat['items'] = new_items
    return raw_cats

def categories_to_plain_items(categories):
    items = []
    for cat in categories:
        items.extend(cat['items'])
    return items