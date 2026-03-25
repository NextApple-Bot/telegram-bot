import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

def is_likely_phone_or_serial(num_str: str) -> bool:
    """Проверка на телефон или серийный номер."""
    clean = re.sub(r'[^\d]', '', num_str)
    if not clean:
        return False
    if 10 <= len(clean) <= 12:
        if clean[0] in ('7', '8', '9'):
            return True
        if len(clean) >= 10:
            return True
    if '+' in num_str and len(clean) >= 10:
        return True
    return False

def extract_payment_amounts(text: str, ignore_prepay: bool = False) -> Dict[str, float]:
    """
    Извлекает суммы платежей, обрабатывая строки по отдельности.
    Игнорирует строки с ценами товаров (Стоимость).
    """
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

    results = {key: 0.0 for key in patterns}
    number_pattern = r'(\d[\d\s]*(?:[.,]\d+)?)'

    # Разбиваем текст на строки
    for line in text.splitlines():
        # Пропускаем строки, содержащие "Стоимость" (цены товаров)
        if re.search(r'Стоимость', line, re.IGNORECASE):
            continue

        for pay_type, keywords in patterns.items():
            for kw in keywords:
                # Ищем "ключ - сумма" в пределах строки
                match = re.search(rf'(?:{kw})\s*[-–—]?\s*{number_pattern}', line, re.IGNORECASE)
                if match:
                    num_str = match.group(1).replace(' ', '').replace(',', '.')
                    try:
                        amount = float(num_str)
                        if not is_likely_phone_or_serial(num_str) and amount <= 10_000_000:
                            results[pay_type] += amount
                            logger.info(f"➕ {pay_type} += {amount} (строка: {line.strip()[:50]})")
                    except ValueError:
                        pass
                    continue  # нашли сумму для этого ключевого слова в строке, дальше не ищем
                # Ищем "сумма - ключ"
                match = re.search(rf'{number_pattern}\s*[-–—]?\s*(?:{kw})', line, re.IGNORECASE)
                if match:
                    num_str = match.group(1).replace(' ', '').replace(',', '.')
                    try:
                        amount = float(num_str)
                        if not is_likely_phone_or_serial(num_str) and amount <= 10_000_000:
                            results[pay_type] += amount
                            logger.info(f"➕ {pay_type} += {amount} (строка: {line.strip()[:50]})")
                    except ValueError:
                        pass

    logger.info(f"📊 Итоговые суммы: {results}")
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
    # ... (остаётся без изменений, тот же код, что и ранее) ...
    # Здесь я не привожу его для краткости, но он должен остаться таким же,
    # как в предыдущей версии (с извлечением телефонов, ФИО и т.д.).
