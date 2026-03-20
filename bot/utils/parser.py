import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def extract_payment_amounts(text: str, ignore_prepay: bool = False) -> Dict[str, float]:
    """
    Извлекает из текста суммы по типам оплаты.
    Возвращает словарь с ключами:
    cash, terminal, qr, transfer, invoice, installment, prepayment
    Если ignore_prepay=True, строки содержащие П/О или предоплату игнорируются.
    """
    patterns = {
        'cash': [r'Наличными', r'Наличные', r'наличными'],
        'terminal': [r'Терминал'],
        'qr': [r'QR[- ]?код', r'QRCode', r'QrCode', r'QR\s*код', r'Qrкод', r'QRCODE', r'Qrcode', r'Qrcod', r'Qr-код', r'Qr-Код'],
        'transfer': [r'Перевод'],
        'invoice': [r'Оплата по счету', r'Оплата По Счету', r'по счету'],
        'installment': [r'Рассрочка'],
    }

    # Добавляем prepayment как отдельный тип, но он будет использоваться только если ignore_prepay=False
    # В итоговом словаре он будет присутствовать всегда

    if ignore_prepay:
        lines = text.splitlines()
        filtered_lines = []
        for line in lines:
            if re.search(r'П[/\\]О|предоплата', line, re.IGNORECASE):
                continue
            filtered_lines.append(line)
        text = '\n'.join(filtered_lines)

    number_pattern = r'(\d[\d\s]*(?:[.,]\d+)?)'
    results = {key: 0.0 for key in patterns}
    results['prepayment'] = 0.0  # добавим prepayment

    # Сначала ищем все числа в тексте
    all_numbers = []
    for match in re.finditer(number_pattern, text):
        num_str = match.group(1).replace(' ', '').replace(',', '.')
        try:
            amount = float(num_str)
            pos = match.start()
            all_numbers.append((amount, pos))
        except ValueError:
            continue

    # Функция для поиска ключевого слова рядом с числом
    def find_keyword_near_number(amount, pos, text, patterns):
        # Проверяем окрестность 50 символов слева и справа
        left = max(0, pos - 50)
        right = min(len(text), pos + len(str(amount)) + 50)
        context = text[left:right]
        for pay_type, keywords in patterns.items():
            for kw in keywords:
                # Ищем ключевое слово в контексте
                if re.search(kw, context, re.IGNORECASE):
                    return pay_type
        # Если не нашли, проверяем наличие предоплаты
        if re.search(r'П[/\\]О|предоплата', context, re.IGNORECASE):
            return 'prepayment'
        return None

    # Обрабатываем каждое число
    for amount, pos in all_numbers:
        pay_type = find_keyword_near_number(amount, pos, text, patterns)
        if pay_type:
            results[pay_type] += amount
        else:
            # Если тип не определён, возможно это просто общая сумма – игнорируем
            pass

    # Дополнительно ищем конструкции вида "ключ - сумма" и "сумма - ключ" (старый метод)
    for pay_type, keywords in patterns.items():
        for kw in keywords:
            # ключ - сумма
            for match in re.finditer(rf'(?:{kw})\s*[-–—]?\s*{number_pattern}', text, re.IGNORECASE):
                num_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    results[pay_type] += float(num_str)
                except ValueError:
                    continue
            # сумма - ключ
            for match in re.finditer(rf'{number_pattern}\s*[-–—]?\s*(?:{kw})', text, re.IGNORECASE):
                num_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    results[pay_type] += float(num_str)
                except ValueError:
                    continue

    # Также ищем prepayment отдельно
    for match in re.finditer(rf'(?:П[/\\]О|предоплата)\s*[-–—]?\s*{number_pattern}', text, re.IGNORECASE):
        num_str = match.group(1).replace(' ', '').replace(',', '.')
        try:
            results['prepayment'] += float(num_str)
        except ValueError:
            continue

    return results

def parse_client_data(text: str) -> dict:
    """
    Извлекает данные клиента из текста сообщения.
    Возвращает словарь с полями:
    full_name, phones, telegram_username, social_network, referral_source, items, payments, total, main_phone.
    """
    result = {
        'full_name': None,
        'phones': [],
        'telegram_username': None,
        'social_network': None,
        'referral_source': None,
        'items': [],
        'payments': {'cash': 0.0, 'terminal': 0.0, 'qr': 0.0, 'installment': 0.0, 'prepayment': 0.0}
    }

    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Телефоны (как в вашем старом коде)
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

        # ФИО (улучшено: ищем после слов "ФИО" или после сумм)
        if not result['full_name']:
            # Сначала ищем явный маркер
            if re.search(r'ФИО|фио|Ф\.И\.О\.', line, re.IGNORECASE):
                parts = line.split(':', 1)
                if len(parts) > 1:
                    result['full_name'] = parts[1].strip()
                else:
                    match = re.search(r'ФИО\s+(.+)', line, re.IGNORECASE)
                    if match:
                        result['full_name'] = match.group(1).strip()
            else:
                # Если есть сумма и строка не содержит другие ключевые слова, возможно это ФИО
                if re.search(r'\d', line):  # есть цифры (сумма)
                    words = line.split()
                    if 2 <= len(words) <= 4 and all(re.match(r'^[А-ЯЁ][а-яё]*$', w) for w in words):
                        result['full_name'] = line

        # Telegram
        if '@' in line and not result['telegram_username']:
            match = re.search(r'@(\w+)', line)
            if match:
                result['telegram_username'] = match.group(1)

        # Соцсети / площадка
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

        # Товары (с серийниками в скобках)
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

        # Суммы
        payments = extract_payment_amounts(line, ignore_prepay=False)
        for typ, val in payments.items():
            if typ in result['payments']:
                result['payments'][typ] += val
            else:
                result['payments'][typ] = val

    # Добавляем недостающие ключи (на случай, если их нет)
    for key in ['transfer', 'invoice']:
        if key not in result['payments']:
            result['payments'][key] = 0.0

    result['total'] = sum(result['payments'].values())
    result['main_phone'] = result['phones'][0] if result['phones'] else None

    return result
