import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

def is_likely_phone_or_serial(num_str: str) -> bool:
    """
    Проверяет, похоже ли число на телефонный номер или серийный номер.
    - Если строка состоит только из цифр и её длина ≥ 10 → True
    - Если строка начинается с 7 или 8 и длина ≥ 10 → True (телефон)
    - Если содержит +7 или 8 в начале → True
    """
    # Убираем все нецифровые символы для проверки
    clean = re.sub(r'[^\d]', '', num_str)
    if not clean:
        return False
    
    # Телефонные номера обычно 10-12 цифр
    if len(clean) >= 10 and len(clean) <= 12:
        # Если начинается с 7, 8 или +7
        if clean.startswith('7') or clean.startswith('8') or clean.startswith('79'):
            return True
        # Если это явно не телефон, но очень длинное число - тоже считаем телефоном
        if len(clean) >= 10:
            return True
    return False

def extract_payment_amounts(text: str, ignore_prepay: bool = False) -> Dict[str, float]:
    patterns = {
        'cash': [r'Наличными', r'Наличные', r'наличными'],
        'terminal': [r'Терминал'],
        'qr': [r'QR[- ]?код', r'QRCode', r'QrCode', r'QR\s*код', r'Qrкод', r'QRCODE', r'Qrcode', r'Qrcod', r'Qr-код', r'Qr-Код'],
        'transfer': [r'Перевод'],
        'invoice': [r'Оплата по счету', r'Оплата По Счету', r'по счету'],
        'installment': [r'Рассрочка'],
    }

    if ignore_prepay:
        lines = []
        for line in text.splitlines():
            if re.search(r'П[/\\]О|предоплата', line, re.IGNORECASE):
                continue
            lines.append(line)
        text = '\n'.join(lines)

    number_pattern = r'(\d[\d\s]*(?:[.,]\d+)?)'
    results = {key: 0.0 for key in patterns}

    numbers = []
    for match in re.finditer(number_pattern, text):
        num_str = match.group(1).replace(' ', '').replace(',', '.')
        try:
            amount = float(num_str)
            # Пропускаем слишком большие суммы (больше 10 млн)
            if amount > 10_000_000:
                logger.info(f"Пропущено слишком большое число: {amount}")
                continue
            # Пропускаем телефоны и серийные номера
            if is_likely_phone_or_serial(num_str):
                logger.info(f"Пропущено число, похожее на телефон/серийник: {num_str}")
                continue
            numbers.append((amount, match.start()))
        except ValueError:
            continue

    for amount, pos in numbers:
        left = max(0, pos - 100)
        right = min(len(text), pos + len(str(int(amount))) + 100)
        context = text[left:right]

        found_type = None
        for pay_type, keywords in patterns.items():
            for kw in keywords:
                if re.search(kw, context, re.IGNORECASE):
                    found_type = pay_type
                    break
            if found_type:
                break

        if found_type:
            results[found_type] += amount

    # Дополнительный проход для паттернов "ключ - сумма"
    for pay_type, keywords in patterns.items():
        for kw in keywords:
            for match in re.finditer(rf'(?:{kw})\s*[-–—]?\s*{number_pattern}', text, re.IGNORECASE):
                num_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    amount = float(num_str)
                    if amount > 10_000_000:
                        logger.info(f"Пропущена большая сумма (ключ-сумма): {amount}")
                        continue
                    if is_likely_phone_or_serial(num_str):
                        logger.info(f"Пропущено число (ключ-сумма), похожее на телефон: {num_str}")
                        continue
                    results[pay_type] += amount
                except ValueError:
                    continue
            for match in re.finditer(rf'{number_pattern}\s*[-–—]?\s*(?:{kw})', text, re.IGNORECASE):
                num_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    amount = float(num_str)
                    if amount > 10_000_000:
                        logger.info(f"Пропущена большая сумма (сумма-ключ): {amount}")
                        continue
                    if is_likely_phone_or_serial(num_str):
                        logger.info(f"Пропущено число (сумма-ключ), похожее на телефон: {num_str}")
                        continue
                    results[pay_type] += amount
                except ValueError:
                    continue

    return results

def extract_prepayments(text: str) -> Dict[str, float]:
    lines = []
    for line in text.splitlines():
        if re.search(r'П[/\\]О|предоплата', line, re.IGNORECASE):
            lines.append(line)
    if not lines:
        return {key: 0.0 for key in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']}
    prepay_text = '\n'.join(lines)
    return extract_payment_amounts(prepay_text, ignore_prepay=False)

def parse_client_data(text: str) -> dict:
    result = {
        'full_name': None,
        'phones': [],
        'telegram_username': None,
        'social_network': None,
        'referral_source': None,
        'items': [],
        'payments': {'cash': 0.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}
    }

    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Расширенный паттерн для поиска телефонов
        phone_pattern = r'(\+?7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
        for match in re.finditer(phone_pattern, line):
            full_number = match.group(0)
            clean_phone = re.sub(r'[\s\-\(\)]', '', full_number)
            if clean_phone.startswith('8'):
                clean_phone = '+7' + clean_phone[1:]
            elif clean_phone.startswith('7') and not clean_phone.startswith('+7'):
                clean_phone = '+7' + clean_phone[1:]
            if clean_phone not in result['phones']:
                result['phones'].append(clean_phone)

        # Извлечение ФИО
        if not result['full_name']:
            if re.search(r'ФИО|фио|Ф\.И\.О\.', line, re.IGNORECASE):
                parts = line.split(':', 1)
                if len(parts) > 1:
                    result['full_name'] = parts[1].strip()
                else:
                    match = re.search(r'ФИО\s+(.+)', line, re.IGNORECASE)
                    if match:
                        result['full_name'] = match.group(1).strip()
            else:
                # Если строка содержит только буквы (русские) и пробелы, и нет цифр
                if not re.search(r'\d', line) and re.match(r'^[А-ЯЁ][а-яё]*(\s+[А-ЯЁ][а-яё]*)*$', line):
                    result['full_name'] = line

        # Telegram username
        if '@' in line and not result['telegram_username']:
            match = re.search(r'@(\w+)', line)
            if match:
                result['telegram_username'] = match.group(1)

        # Соцсети/площадка
        if re.search(r'соц\s*сети|social|площадка', line, re.IGNORECASE):
            parts = line.split(':', 1)
            if len(parts) > 1:
                result['social_network'] = parts[1].strip()
            else:
                match = re.search(r'[—-]\s*(.+)', line)
                if match:
                    result['social_network'] = match.group(1).strip()

        # Откуда узнал
        if re.search(r'как\s+о\s+нас\s+узнал|откуда|referral', line, re.IGNORECASE):
            parts = line.split(':', 1)
            if len(parts) > 1:
                result['referral_source'] = parts[1].strip()

        # Товары
        if re.search(r'\([A-Z0-9-]{5,}\)', line):
            item_text = line
            price_match = re.search(r'(\d[\d\s]*[.,]?\d*)\s*(?:₽|руб|рублей|р\.?)', line, re.IGNORECASE)
            if price_match:
                price_str = price_match.group(1).replace(' ', '').replace(',', '.')
                try:
                    price = float(price_str)
                except ValueError:
                    price = None
            else:
                price = None
            result['items'].append({'item_text': item_text, 'price': price})

        # Платежи
        payments = extract_payment_amounts(line, ignore_prepay=False)
        for typ, val in payments.items():
            if typ in result['payments']:
                result['payments'][typ] += val
            else:
                result['payments'][typ] = val

    for key in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']:
        if key not in result['payments']:
            result['payments'][key] = 0.0

    result['total'] = sum(result['payments'].values())
    result['main_phone'] = result['phones'][0] if result['phones'] else None

    return result
