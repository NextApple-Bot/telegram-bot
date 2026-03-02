import json
import os
from datetime import datetime

FINANCES_FILE = "finances.json"

def load_finances():
    if os.path.exists(FINANCES_FILE):
        with open(FINANCES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {
            "date": None,
            "terminal": 0,
            "cash": 0,
            "qr": 0,
            "total": 0
        }

def save_finances(data):
    with open(FINANCES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def check_and_reset(data):
    today = datetime.now().strftime("%Y-%m-%d")
    if data["date"] != today:
        data["date"] = today
        data["terminal"] = 0
        data["cash"] = 0
        data["qr"] = 0
        data["total"] = 0
    return data

def add_payment(payment_type, amount):
    data = load_finances()
    data = check_and_reset(data)
    if payment_type in ("terminal", "cash", "qr"):
        data[payment_type] += amount
        data["total"] += amount
    save_finances(data)

def get_finances():
    data = load_finances()
    data = check_and_reset(data)
    return data

def reset_finances():
    data = load_finances()
    data = check_and_reset(data)
    data["terminal"] = 0
    data["cash"] = 0
    data["qr"] = 0
    data["total"] = 0
    save_finances(data)
