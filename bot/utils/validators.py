import re
from typing import List

def extract_serials(text: str) -> List[str]:
    """
    Извлекает все серийные номера из текста (из круглых скобок).
    Возвращает список уникальных серийных номеров в верхнем регистре (для буквенно-цифровых).
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

def normalize_serial(serial: str) -> str:
    """Приводит серийный номер к стандартному виду (без пробелов, в верхнем регистре)."""
    if not serial:
        return ""
    return re.sub(r'\s+', '', serial).upper()
