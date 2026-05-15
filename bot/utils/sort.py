import re
from typing import Dict, List, Any

def detect_sim_type(text: str) -> str:
    """Определяет тип SIM-карты по тексту товара."""
    text_lower = text.lower()
    if any(word in text_lower for word in ["esim", "e-sim", "е-сим"]):
        return "eSIM"
    if any(word in text_lower for word in ["nano", "нано"]):
        return "Nano"
    if any(word in text_lower for word in ["dual", "2 sim", "две сим"]):
        return "Dual"
    return "other"


def get_full_model_name(text: str) -> str:
    """Извлекает чистое название модели (до первого пробела или скобки)."""
    # Убираем всё после первого пробела или скобки
    match = re.match(r'^([^(]+)', text.strip())
    if match:
        return match.group(1).strip()
    return text.strip()


def build_output_text(categories: List[Dict[str, Any]]) -> str:
    """
    Формирует красивый текстовый вывод ассортимента для отправки в .txt файл.
    """
    lines = []
    lines.append("📦 ТЕКУЩИЙ АССОРТИМЕНТ")
    lines.append("=" * 50)
    lines.append(f"Дата выгрузки: {__import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')}\n")

    total_items = 0

    for cat in categories:
        cat_name = cat["name"]
        items = cat.get("items", [])
        
        if not items:
            continue  # пропускаем пустые категории

        lines.append(f"\n🔹 {cat_name} ({len(items)} шт.)")
        lines.append("-" * 40)

        for item in items:
            price_str = f"{item['price']:,} ₽".replace(",", " ") if item.get('price') else "—"
            status = "🔒 ЗАБРОНИРОВАНО" if item.get("is_booked") else "✅ В наличии"
            
            booking_info = f" | {item['booking_info']}" if item.get("booking_info") else ""
            serial = f" | S/N: {item['serial']}" if item.get("serial") else ""

            line = f"• {item['text']}"
            if price_str != "—":
                line += f" — {price_str}"
            line += f"  {status}{booking_info}{serial}"
            lines.append(line)

            total_items += 1

    lines.append("\n" + "=" * 50)
    lines.append(f"Итого товаров: {total_items}")
    lines.append(f"Итого категорий: {len([c for c in categories if c.get('items')])}")

    return "\n".join(lines)


def sort_items_by_name(items: List[Dict]) -> List[Dict]:
    """Сортировка товаров по названию (естественная сортировка)."""
    def natural_key(text: str):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
    
    return sorted(items, key=lambda x: natural_key(x.get("text", "")))


def group_by_model(items: List[Dict]) -> Dict[str, List[Dict]]:
    """Группирует товары по модели (для отчётов по остаткам)."""
    groups = {}
    for item in items:
        model = get_full_model_name(item["text"])
        if model not in groups:
            groups[model] = []
        groups[model].append(item)
    return groups
