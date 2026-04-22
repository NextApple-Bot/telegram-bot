# Файл: bot/services/payment_parser.py
import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

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
        # Ищем ключевые слова в строке
        line_pay_types = [pt for pt, kw in PAYMENT_KEYWORDS.items() if kw.search(line)]
        if not line_pay_types:
            continue

        # Ищем все числа в строке
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

        # Если в строке один тип оплаты и одно число — связываем их
        if len(line_pay_types) == 1 and len(numbers) == 1:
            results[line_pay_types[0]] += numbers[0]
        # Если несколько чисел или несколько типов — пытаемся определить по близости
        else:
            # Упрощённо: первое число первому типу, остальные пропускаем (или можно добавить эвристики)
            for pt, num in zip(line_pay_types, numbers):
                results[pt] += num
            # Оставшиеся числа (если их больше) игнорируем, чтобы не приписывать лишнего

    return results


def extract_prepayments(text: str) -> Dict[str, float]:
    """Извлекает суммы предоплаты (строки с П/О или предоплата)."""
    lines = [line for line in text.splitlines() if PREPAY_PATTERN.search(line)]
    if not lines:
        return {key: 0.0 for key in PAYMENT_KEYWORDS}

    prepay_text = '\n'.join(lines)
    return extract_payment_amounts(prepay_text, ignore_prepay=False)
