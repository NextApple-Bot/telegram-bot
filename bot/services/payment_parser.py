# Файл: bot/services/payment_parser.py
import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Предкомпилированные регулярные выражения
PAYMENT_KEYWORDS = {
    'cash': re.compile(r'Наличными|Наличные|наличными', re.IGNORECASE),
    'terminal': re.compile(r'Терминал', re.IGNORECASE),
    'qr': re.compile(r'QR[- ]?код|QRCode|QrCode|QR\s*код|Qrкод|QRCODE|Qrcode|Qrcod|Qr-код|Qr-Код|Qr-code|QR-code', re.IGNORECASE),
    'transfer': re.compile(r'Перевод', re.IGNORECASE),
    'invoice': re.compile(r'Оплата по счету|Оплата По Счету|по счету', re.IGNORECASE),
    'installment': re.compile(r'Рассрочка', re.IGNORECASE),
}
PREPAY_PATTERN = re.compile(r'П[/\\]О|предоплата', re.IGNORECASE)
NUMBER_PATTERN = re.compile(r'(\d[\d\s]*(?:[.,]\d+)?)')
BRACKET_PAYMENT_PATTERN = re.compile(r'\(([^)]+)\)')


def is_likely_phone_or_serial(num_str: str) -> bool:
    if not num_str.isdigit():
        return False
    if len(num_str) >= 10:
        if num_str.startswith('7') or num_str.startswith('8'):
            return True
        return True
    return False


def extract_payment_amounts(text: str, ignore_prepay: bool = False) -> Dict[str, float]:
    """Извлекает суммы оплаты из текста. Возвращает словарь с типами платежей."""
    if ignore_prepay:
        lines = [line for line in text.splitlines() if not PREPAY_PATTERN.search(line)]
        text = '\n'.join(lines)

    lines = text.splitlines()
    results = {key: 0.0 for key in PAYMENT_KEYWORDS}

    for line in lines:
        for match in NUMBER_PATTERN.finditer(line):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
            except ValueError:
                continue

            if amount > 10_000_000:
                logger.debug(f"Пропущено слишком большое число: {amount}")
                continue
            if is_likely_phone_or_serial(num_str):
                logger.debug(f"Пропущено число, похожее на телефон/серийник: {num_str}")
                continue

            # Проверка на скобки без ключевого слова
            open_paren = line.rfind('(', 0, match.start())
            if open_paren != -1:
                close_paren = line.find(')', match.start() + len(match.group()))
                if close_paren != -1 and close_paren > open_paren:
                    bracket_content = line[open_paren+1:close_paren]
                    found_keyword = any(kw_re.search(bracket_content) for kw_re in PAYMENT_KEYWORDS.values())
                    if not found_keyword:
                        logger.debug(f"Пропущено число в скобках без ключевого слова оплаты: {num_str}")
                        continue

            for pay_type, kw_re in PAYMENT_KEYWORDS.items():
                if kw_re.search(line):
                    results[pay_type] += amount
                    logger.debug(f"➕ {pay_type} += {amount}")
                    break

    return results


def extract_prepayments(text: str) -> Dict[str, float]:
    """Извлекает суммы предоплаты (строки с П/О или предоплата)."""
    lines = [line for line in text.splitlines() if PREPAY_PATTERN.search(line)]
    if not lines:
        return {key: 0.0 for key in PAYMENT_KEYWORDS}

    prepay_text = '\n'.join(lines)
    payments = extract_payment_amounts(prepay_text, ignore_prepay=False)

    # Если стандартная обработка не дала результатов, пытаемся явно извлечь тип из скобок
    if all(v == 0 for v in payments.values()):
        for line in lines:
            match_num = NUMBER_PATTERN.search(line)
            if not match_num:
                continue
            num_str = match_num.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
            except ValueError:
                continue

            match_bracket = BRACKET_PAYMENT_PATTERN.search(line)
            if match_bracket:
                bracket_content = match_bracket.group(1).strip().lower()
                if re.search(r'нал|cash', bracket_content):
                    payments['cash'] += amount
                elif re.search(r'терминал|terminal', bracket_content):
                    payments['terminal'] += amount
                elif re.search(r'qr|qrcode|qr-?code', bracket_content):
                    payments['qr'] += amount
                elif re.search(r'перевод|transfer', bracket_content):
                    payments['transfer'] += amount
                elif re.search(r'счет|invoice', bracket_content):
                    payments['invoice'] += amount
                elif re.search(r'рассрочка|installment', bracket_content):
                    payments['installment'] += amount
                else:
                    for pay_type, kw_re in PAYMENT_KEYWORDS.items():
                        if kw_re.search(line):
                            payments[pay_type] += amount
                            break
            else:
                for pay_type, kw_re in PAYMENT_KEYWORDS.items():
                    if kw_re.search(line):
                        payments[pay_type] += amount
                        break
    return payments
