import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

def is_likely_phone_or_serial(num_str: str) -> bool:
    """
    Проверяет, похоже ли число на телефонный номер или серийный номер.
    """
    if not num_str.isdigit():
        return False
    if len(num_str) >= 10:
        if num_str.startswith('7') or num_str.startswith('8'):
            return True
        return True
    return False

def extract_payment_amounts(text: str, ignore_prepay: bool = False) -> Dict[str, float]:
    """
    Извлекает суммы оплаты из текста.
    Возвращает словарь с ключами: cash, terminal, qr, transfer, invoice, installment.
    Если ignore_prepay=True, строки с П/О или предоплатой удаляются.
    """
    patterns = {
        'cash': [r'Наличными', r'Наличные', r'наличными'],
        'terminal': [r'Терминал'],
        'qr': [r'QR[- ]?код', r'QRCode', r'QrCode', r'QR\s*код', r'Qrкод', r'QRCODE', r'Qrcode', r'Qrcod', r'Qr-код', r'Qr-Код'],
        'transfer': [r'Перевод'],
        'invoice': [r'Оплата по счету', r'Оплата По Счету', r'по счету'],
        'installment': [r'Рассрочка'],
    }

    # 1. Удаление строк с предоплатой (если требуется)
    if ignore_prepay:
        lines = []
        for line in text.splitlines():
            if re.search(r'П[/\\]О|предоплата', line, re.IGNORECASE):
                continue
            lines.append(line)
        text = '\n'.join(lines)

    # 2. Разбиваем текст на строки для точного позиционирования
    lines = text.splitlines()
    results = {key: 0.0 for key in patterns}

    # 3. Проходим по каждой строке отдельно
    for line in lines:
        # Ищем все числа в строке
        for match in re.finditer(r'(\d[\d\s]*(?:[.,]\d+)?)', line):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
            except ValueError:
                continue

            # Фильтр 1: слишком большие суммы (> 10 млн)
            if amount > 10_000_000:
                logger.info(f"Пропущено слишком большое число: {amount}")
                continue

            # Фильтр 2: телефонные номера и серийники
            if is_likely_phone_or_serial(num_str):
                logger.info(f"Пропущено число, похожее на телефон/серийник: {num_str}")
                continue

            # Фильтр 3: число в скобках без ключевого слова оплаты
            # Найдём открывающую и закрывающую скобку, если число внутри них
            open_paren = line.rfind('(', 0, match.start())
            if open_paren != -1:
                close_paren = line.find(')', match.start() + len(match.group()))
                if close_paren != -1 and close_paren > open_paren:
                    bracket_content = line[open_paren+1:close_paren]
                    # Проверяем, есть ли в скобках ключевое слово оплаты
                    found_keyword = False
                    for kw_list in patterns.values():
                        for kw in kw_list:
                            if re.search(kw, bracket_content, re.IGNORECASE):
                                found_keyword = True
                                break
                        if found_keyword:
                            break
                    if not found_keyword:
                        logger.info(f"Пропущено число в скобках без ключевого слова оплаты: {num_str}")
                        continue

            # Определяем тип оплаты: ищем ключевое слово в этой же строке
            found_type = None
            for pay_type, keywords in patterns.items():
                for kw in keywords:
                    if re.search(kw, line, re.IGNORECASE):
                        found_type = pay_type
                        break
                if found_type:
                    break

            if found_type:
                results[found_type] += amount
                logger.info(f"➕ {found_type} += {amount} (строка: {line[:80]})")
            else:
                # Если тип не найден, возможно это общая сумма – игнорируем
                pass

    return results

def extract_prepayments(text: str) -> Dict[str, float]:
    """
    Извлекает суммы предоплаты (строки с П/О или предоплата) и определяет тип оплаты.
    Возвращает словарь с ключами: cash, terminal, qr, transfer, invoice, installment.
    """
    lines = []
    for line in text.splitlines():
        if re.search(r'П[/\\]О|предоплата', line, re.IGNORECASE):
            lines.append(line)
    if not lines:
        return {key: 0.0 for key in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']}
    prepay_text = '\n'.join(lines)
    return extract_payment_amounts(prepay_text, ignore_prepay=False)

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
        'payments': {'cash': 0.0, 'terminal': 0.0, 'qr': 0.0, 'transfer': 0.0, 'invoice': 0.0, 'installment': 0.0}
    }

    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Телефоны
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

        # ФИО
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
                if re.search(r'\d', line):
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

        # Суммы – используем основную функцию (для продаж)
        payments = extract_payment_amounts(line, ignore_prepay=False)
        for typ, val in payments.items():
            if typ in result['payments']:
                result['payments'][typ] += val
            else:
                result['payments'][typ] = val

    # Гарантируем наличие всех ключей
    for key in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']:
        if key not in result['payments']:
            result['payments'][key] = 0.0

    result['total'] = sum(result['payments'].values())
    result['main_phone'] = result['phones'][0] if result['phones'] else None

    return result
