# Файл: bot/utils/validators.py
import re
from typing import List

def extract_serials(text: str) -> List[str]:
    """
    Извлекает серийные номера из текста.
    Серийный номер ищется внутри круглых скобок.
    Возвращает список уникальных серийных номеров (без изменений, в исходном регистре,
    но для единообразия можно привести к верхнему).
    """
    if not isinstance(text, str):
        return []
    serials = set()
    # Ищем всё, что внутри круглых скобок (не вложенных)
    matches = re.finditer(r'\(([^)]+)\)', text)
    for match in matches:
        candidate = match.group(1).strip()
        if not candidate:
            continue
        # Минимальная длина серийного номера — 5 символов, максимальная — 50
        if 5 <= len(candidate) <= 50:
            serials.add(candidate)   # сохраняем как есть (можно .upper() при желании)
    return list(serials)

def normalize_serial(serial: str) -> str:
    """Приводит серийный номер к стандартному виду (без пробелов, в верхнем регистре)."""
    if not serial:
        return ""
    return re.sub(r'\s+', '', serial).upper()
