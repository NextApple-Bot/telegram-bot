import re

def extract_serial(line: str) -> str | None:
    """
    Извлекает серийный номер из строки товара.
    - Если в скобках есть символ '№', возвращает всё содержимое скобок.
    - Иначе ищет комбинацию букв и цифр (длиной от 5 символов) или длинное число (≥10 цифр).
    Возвращает нормализованный серийный номер (верхний регистр, обрезанный) или None.
    """
    matches = re.finditer(r'\(([^)]+)\)', line)
    for match in matches:
        candidate = match.group(1).strip()
        if '№' in candidate:
            return candidate.upper()
        if re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            if len(candidate) >= 5:
                return candidate.upper()
        if candidate.isdigit() and len(candidate) >= 10:
            return candidate
    return None

def extract_serials_from_text(text: str) -> list[str]:
    """
    Извлекает все серийные номера из текста сообщения (для продаж).
    Работает аналогично extract_serial, но возвращает список уникальных номеров.
    """
    serials = set()
    matches = re.finditer(r'\(([^)]+)\)', text)
    for match in matches:
        candidate = match.group(1).strip()
        if '№' in candidate:
            serials.add(candidate.upper())
        elif re.search(r'[A-Za-z]', candidate) and re.search(r'[0-9]', candidate):
            if len(candidate) >= 5:
                serials.add(candidate.upper())
        elif candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
    return list(serials)
