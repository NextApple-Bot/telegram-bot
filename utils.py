import re
from typing import Dict, List, Tuple

def extract_payment_amounts(text: str, ignore_prepay: bool = False) -> Dict[str, float]:
    """
    Извлекает из текста суммы по типам оплаты.
    Возвращает словарь с ключами:
    cash, terminal, qr, transfer, invoice, installment
    Если ignore_prepay=True, строки содержащие П/О или предоплату игнорируются.
    """
    # Определяем ключевые слова для каждого типа оплаты
    patterns = {
        'cash': [r'Наличными', r'Наличные', r'наличными'],
        'terminal': [r'Терминал'],
        'qr': [r'QR[- ]?код', r'QRCode', r'QrCode', r'QR\s*код', r'Qrкод', r'QRCODE'],
        'transfer': [r'Перевод'],
        'invoice': [r'Оплата по счету', r'Оплата По Счету', r'по счету'],
        'installment': [r'Рассрочка'],
    }

    # Если нужно игнорировать предоплату, удаляем строки с П/О
    if ignore_prepay:
        lines = text.splitlines()
        filtered_lines = []
        for line in lines:
            if re.search(r'П[/\\]О|предоплата', line, re.IGNORECASE):
                continue
            filtered_lines.append(line)
        text = '\n'.join(filtered_lines)

    # Числовой паттерн: целые или десятичные, с пробелами в качестве разделителей тысяч
    number_pattern = r'(\d[\d\s]*(?:[.,]\d+)?)'

    results = {key: 0.0 for key in patterns}

    # Ищем вхождения "ключ - сумма" и "сумма - ключ"
    for pay_type, keywords in patterns.items():
        for kw in keywords:
            # Вариант: ключ дефис сумма
            for match in re.finditer(rf'(?:{kw})\s*[-–—]?\s*{number_pattern}', text, re.IGNORECASE):
                num_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    amount = float(num_str)
                    results[pay_type] += amount
                except ValueError:
                    continue
            # Вариант: сумма дефис ключ
            for match in re.finditer(rf'{number_pattern}\s*[-–—]?\s*(?:{kw})', text, re.IGNORECASE):
                num_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    amount = float(num_str)
                    results[pay_type] += amount
                except ValueError:
                    continue

    return results
