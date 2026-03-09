import re
from utils import extract_all_amounts
from inventory import extract_serials_from_text

def parse_client_data(text: str) -> dict:
    """
    Извлекает из текста:
    - телефон
    - ФИО
    - Telegram username
    - Соцсети
    - Откуда узнал
    - Товары (строки с серийными номерами и ценами)
    - Суммы и способы оплаты
    Возвращает словарь с данными клиента и списком товаров.
    """
    result = {
        'full_name': None,
        'phone': None,
        'telegram_username': None,
        'social_network': None,
        'referral_source': None,
        'items': [],          # список словарей: {'item_text': str, 'price': float}
        'payments': {'cash': 0.0, 'terminal': 0.0, 'qr': 0.0, 'installment': 0.0, 'prepayment': 0.0}
    }

    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # --- Извлечение телефона ---
        # Ищем последовательности, похожие на телефон: +7... , 8..., 7...
        phone_match = re.search(r'(\+?7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', line)
        if phone_match and not result['phone']:
            raw_phone = phone_match.group(0)
            clean_phone = re.sub(r'[\s\-\(\)]', '', raw_phone)
            if clean_phone.startswith('8'):
                clean_phone = '+7' + clean_phone[1:]
            elif clean_phone.startswith('7') and not clean_phone.startswith('+7'):
                clean_phone = '+7' + clean_phone[1:]
            result['phone'] = clean_phone

        # --- Извлечение ФИО ---
        if not result['full_name']:
            # Ищем после слов "ФИО", "фио"
            if re.search(r'ФИО|фио|Ф\.И\.О\.', line, re.IGNORECASE):
                parts = line.split(':', 1)
                if len(parts) > 1:
                    result['full_name'] = parts[1].strip()
                else:
                    match = re.search(r'ФИО\s+(.+)', line, re.IGNORECASE)
                    if match:
                        result['full_name'] = match.group(1).strip()
            else:
                # Проверяем, не является ли строка именем (2-4 слова, только буквы)
                words = line.split()
                if 2 <= len(words) <= 4 and all(re.match(r'^[А-ЯЁ][а-яё]*$', w) for w in words):
                    result['full_name'] = line

        # --- Telegram username ---
        if '@' in line and not result['telegram_username']:
            match = re.search(r'@(\w+)', line)
            if match:
                result['telegram_username'] = match.group(1)

        # --- Соцсети / площадка ---
        if re.search(r'соц\s*сети|social|площадка', line, re.IGNORECASE):
            parts = line.split(':', 1)
            if len(parts) > 1:
                result['social_network'] = parts[1].strip()
            else:
                match = re.search(r'[—-]\s*(.+)', line)
                if match:
                    result['social_network'] = match.group(1).strip()

        # --- Откуда узнал ---
        if re.search(r'как\s+о\s+нас\s+узнал|откуда|referral', line, re.IGNORECASE):
            parts = line.split(':', 1)
            if len(parts) > 1:
                result['referral_source'] = parts[1].strip()

        # --- Товары: строки с серийным номером в скобках ---
        if re.search(r'\([A-Z0-9-]{5,}\)', line):
            # Это строка товара
            item_text = line
            # Ищем цену в этой строке или в следующих (но проще взять из общей суммы)
            price_match = re.search(r'(\d[\d\s]*[.,]?\d*)\s*(?:₽|руб|рублей|р\.?)', line, re.IGNORECASE)
            if price_match:
                price_str = price_match.group(1).replace(' ', '').replace(',', '.')
                try:
                    price = float(price_str)
                except:
                    price = None
            else:
                price = None
            result['items'].append({'item_text': item_text, 'price': price})

        # --- Строки с ценами и способами оплаты ---
        amounts = extract_all_amounts(line)
        for typ, val in amounts:
            if typ in result['payments']:
                result['payments'][typ] += val
            elif typ == 'prepayment':
                result['payments']['prepayment'] += val

    # Вычисляем общую сумму как сумму всех платежей
    result['total'] = sum(result['payments'].values())
    return result
