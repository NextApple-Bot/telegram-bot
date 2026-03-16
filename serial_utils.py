import re

def extract_serials(text: str) -> list[str]:
    """
    Извлекает все серийные номера из текста.
    Ищет содержимое круглых скобок, удовлетворяющее условиям:
    - содержит символ '№'
    - содержит и буквы, и цифры, длина >= 5
    - состоит только из цифр, длина >= 10
    Возвращает список уникальных серийных номеров (в верхнем регистре для буквенно-цифровых).
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

# Для обратной совместимости (если где-то используется старое имя)
extract_serials_from_text = extract_serials
