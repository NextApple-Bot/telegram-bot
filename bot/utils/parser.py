import re
import logging
from typing import Dict

logger = logging.getLogger(__name__)

def is_likely_phone_or_serial(num_str: str) -> bool:
    """
    Проверяет, похоже ли число на телефонный номер или серийный номер.
    """
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
    added_sums = []  # для логирования

    numbers = []
    for match in re.finditer(number_pattern, text):
        num_str = match.group(1).replace(' ', '').replace(',', '.')
        try:
            amount = float(num_str)
            if amount > 10_000_000:
                logger.info(f"⛔ Пропущено слишком большое число: {amount} (телефон/серийник?)")
                continue
            if is_likely_phone_or_serial(num_str):
                logger.info(f"⛔ Пропущено число, похожее на телефон/серийник: {num_str}")
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
            added_sums.append(f"{found_type} += {amount} (контекст: {context[:50]}...)")
            logger.info(f"➕ {found_type} += {amount} (контекст: {context[:80]})")
        else:
            logger.info(f"⚠️ Найдено число {amount}, но нет ключевого слова в контексте. Игнорируем.")

    # Дополнительный проход для паттернов "ключ - сумма"
    for pay_type, keywords in patterns.items():
        for kw in keywords:
            for match in re.finditer(rf'(?:{kw})\s*[-–—]?\s*{number_pattern}', text, re.IGNORECASE):
                num_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    amount = float(num_str)
                    if amount > 10_000_000:
                        logger.info(f"⛔ Пропущена большая сумма (ключ-сумма): {amount}")
                        continue
                    if is_likely_phone_or_serial(num_str):
                        logger.info(f"⛔ Пропущено число (ключ-сумма), похожее на телефон: {num_str}")
                        continue
                    results[pay_type] += amount
                    added_sums.append(f"{pay_type} += {amount} (ключ-сумма)")
                    logger.info(f"➕ {pay_type} += {amount} (ключ-сумма)")
                except ValueError:
                    continue
            for match in re.finditer(rf'{number_pattern}\s*[-–—]?\s*(?:{kw})', text, re.IGNORECASE):
                num_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    amount = float(num_str)
                    if amount > 10_000_000:
                        logger.info(f"⛔ Пропущена большая сумма (сумма-ключ): {amount}")
                        continue
                    if is_likely_phone_or_serial(num_str):
                        logger.info(f"⛔ Пропущено число (сумма-ключ), похожее на телефон: {num_str}")
                        continue
                    results[pay_type] += amount
                    added_sums.append(f"{pay_type} += {amount} (сумма-ключ)")
                    logger.info(f"➕ {pay_type} += {amount} (сумма-ключ)")
                except ValueError:
                    continue

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
    # ... (оставляем как было, без изменений) ...
    # Тот же код, что и в вашем файле (я не меняю его здесь для краткости)
