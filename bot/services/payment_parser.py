# Файл: bot/services/payment_parser.py
import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# Приоритеты: специфичные типы должны иметь преимущество над общим "cash"
PAYMENT_KEYWORDS = {
    'terminal': re.compile(r'Терминал|Терминалом|терминал|терминалом|Terminal|terminal|Терм\.?', re.IGNORECASE),
    'qr': re.compile(r'QR[- ]?код|QRCode|QrCode|QR\s*код|Qrкод|QRCODE|Qrcode|Qrcod|Qr-код|Qr-Код|Qr-code|QR-code', re.IGNORECASE),
    'transfer': re.compile(r'Перевод|перевод|Переводом|переводом|Пер\.?', re.IGNORECASE),
    'invoice': re.compile(r'Оплата по счету|Оплата По Счету|по счету|По счёту|Счёт|Счет|Инвойс', re.IGNORECASE),
    'installment': re.compile(r'Рассрочка|рассрочка|Рассрочкой|рассрочкой|Расср\.?', re.IGNORECASE),
    'cash': re.compile(r'Наличными|Наличные|наличными|нал\.?|нал\b|Нал\b|Наличка', re.IGNORECASE),  # \b чтобы не цеплять "нал" внутри слов
}
PREPAY_PATTERN = re.compile(r'П[/\\]О|предоплата', re.IGNORECASE)
NUMBER_PATTERN = re.compile(r'(\d[\d\s]*(?:[.,]\d+)?)')
BRACKET_PAYMENT_PATTERN = re.compile(r'\(([^)]+)\)')


def is_likely_phone_or_serial(num_str: str) -> bool:
    """Проверяет, похоже ли число на телефонный номер или серийный номер."""
    if not num_str.isdigit():
        return False
    if len(num_str) >= 10:
        return True
    return False


def extract_payment_amounts(text: str, ignore_prepay: bool = False) -> Dict[str, float]:
    """
    Извлекает суммы оплаты из текста. Возвращает словарь с типами платежей.
    """
    if ignore_prepay:
        lines = [line for line in text.splitlines() if not PREPAY_PATTERN.search(line)]
        text = '\n'.join(lines)

    lines = text.splitlines()
    results = {key: 0.0 for key in PAYMENT_KEYWORDS}

    for line in lines:
        # Находим все типы оплаты, упомянутые в строке
        found_types = {pt: kw.search(line) for pt, kw in PAYMENT_KEYWORDS.items()}
        line_pay_types = [pt for pt, match in found_types.items() if match]

        if not line_pay_types:
            continue

        # Если в строке есть специфичные типы (не cash), исключаем cash
        specific_types = [pt for pt in line_pay_types if pt != 'cash']
        if specific_types:
            # Оставляем только специфичные типы
            line_pay_types = specific_types

        # Извлекаем все числа из строки
        numbers = []
        for match in NUMBER_PATTERN.finditer(line):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
            except ValueError:
                continue
            if amount > 10_000_000 or is_likely_phone_or_serial(num_str):
                continue
            numbers.append(amount)

        if not numbers:
            continue

        # Если один тип оплаты и одно число — связываем их
        if len(line_pay_types) == 1 and len(numbers) == 1:
            results[line_pay_types[0]] += numbers[0]
        else:
            # Иначе пытаемся сопоставить по порядку
            for pt, num in zip(line_pay_types, numbers):
                results[pt] += num

    return results


def extract_prepayments(text: str) -> Dict[str, float]:
    """Извлекает суммы предоплаты (строки с П/О или предоплата)."""
    lines = [line for line in text.splitlines() if PREPAY_PATTERN.search(line)]
    if not lines:
        return {key: 0.0 for key in PAYMENT_KEYWORDS}

    prepay_text = '\n'.join(lines)
    return extract_payment_amounts(prepay_text, ignore_prepay=False)
