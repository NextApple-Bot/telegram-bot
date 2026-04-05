# Файл: bot/utils/validators.py
import re
from typing import List

def extract_serials(text: str) -> List[str]:
    if not isinstance(text, str):
        return []
    serials = set()
    matches = re.finditer(r'\(([^)]+)\)', text)
    for match in matches:
        candidate = match.group(1).strip()
        if not candidate:
            continue
        # Если есть символ '№' – сразу добавляем
        if '№' in candidate:
            serials.add(candidate.upper())
        # Только буквы и цифры, длина 5-30
        elif re.fullmatch(r'[A-Za-z0-9]{5,30}', candidate):
            serials.add(candidate.upper())
        # Только цифры, длина >= 10
        elif candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
        # Буквы, цифры и дефисы, длина 5-30
        elif '-' in candidate and re.fullmatch(r'[A-Za-z0-9\-]{5,30}', candidate):
            serials.add(candidate.upper())
    return list(serials)

def normalize_serial(serial: str) -> str:
    if not serial:
        return ""
    return re.sub(r'\s+', '', serial).upper()
