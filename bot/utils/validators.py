import re
from typing import List

def extract_serials(text: str) -> List[str]:
    """
    Извлекает серийные номера из текста.
    Ищет содержимое круглых скобок, которое:
    - содержит символ '№' (любая длина)
    - ИЛИ состоит только из букв и цифр (A-Z, a-z, 0-9) длиной от 5 до 30 символов
    - ИЛИ состоит только из цифр длиной от 10 символов (для старых форматов)
    Возвращает список уникальных серийных номеров в верхнем регистре.
    """
    serials = set()
    matches = re.finditer(r'\(([^)]+)\)', text)
    for match in matches:
        candidate = match.group(1).strip()
        # Если есть символ '№' – сразу добавляем
        if '№' in candidate:
            serials.add(candidate.upper())
        # Если состоит только из букв и цифр, длина 5-30 символов
        elif re.fullmatch(r'[A-Za-z0-9]{5,30}', candidate):
            serials.add(candidate.upper())
        # Если только цифры и длина >= 10
        elif candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
    return list(serials)

def normalize_serial(serial: str) -> str:
    """Приводит серийный номер к стандартному виду (без пробелов, в верхнем регистре)."""
    if not serial:
        return ""
    return re.sub(r'\s+', '', serial).upper()
