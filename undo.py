import json
import os

UNDO_FILE = "last_action.json"

def save_action(action_type, data):
    """
    Сохраняет последнее действие.
    action_type: "sales", "preorder", "booking"
    data: словарь с информацией для отката
    """
    with open(UNDO_FILE, 'w', encoding='utf-8') as f:
        json.dump({"type": action_type, "data": data}, f, ensure_ascii=False, indent=2)

def clear_action():
    if os.path.exists(UNDO_FILE):
        os.remove(UNDO_FILE)

def get_action():
    if os.path.exists(UNDO_FILE):
        with open(UNDO_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None
