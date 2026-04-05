# Файл: bot/utils/validators.py
import re
from typing import List

def extract_serials(text: str) -> List[str]:
    """
    Извлекает серийные номера из текста.
    Возвращает список уникальных серийных номеров в верхнем регистре.
    """
    if not isinstance(text, str):
        return []
    serials = set()
    matches = re.finditer(r'\(([^)]+)\)', text)
    for match in matches:
        candidate = match.group(1)
        if candidate is None:
            continue
        candidate = candidate.strip()
        if not candidate:
            continue
        # Если есть символ '№' – сразу добавляем
        if '№' in candidate:
            serials.add(candidate.upper())
        # Если состоит только из букв и цифр, длина 5-30
        elif re.fullmatch(r'[A-Za-z0-9]{5,30}', candidate):
            serials.add(candidate.upper())
        # Если только цифры и длина >= 10
        elif candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
        # НОВОЕ: если содержит дефис, состоит из букв, цифр и дефисов, длина 5-30
        elif '-' in candidate and re.fullmatch(r'[A-Za-z0-9\-]{5,30}', candidate):
            serials.add(candidate.upper())
    return list(serials)

def normalize_serial(serial: str) -> str:
    """Приводит серийный номер к стандартному виду (без пробелов, в верхнем регистре)."""
    if not serial:
        return ""
    return re.sub(r'\s+', '', serial).upper()
