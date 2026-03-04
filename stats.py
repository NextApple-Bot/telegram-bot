import json
import os
from datetime import datetime

STATS_FILE = "stats.json"

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {
            "date": None,
            "preorders": 0,
            "bookings": 0,
            "sales": 0,
            "preorders_cash": 0.0,
            "preorders_terminal": 0.0,
            "preorders_qr": 0.0,
            "preorders_installment": 0.0,
            "bookings_total": 0.0,
            "sales_cash": 0.0,
            "sales_terminal": 0.0,
            "sales_qr": 0.0,
            "sales_installment": 0.0,
        }

def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def check_and_reset(stats):
    today = datetime.now().strftime("%Y-%m-%d")
    if stats["date"] != today:
        stats["date"] = today
        stats["preorders"] = 0
        stats["bookings"] = 0
        stats["sales"] = 0
        stats["preorders_cash"] = 0.0
        stats["preorders_terminal"] = 0.0
        stats["preorders_qr"] = 0.0
        stats["preorders_installment"] = 0.0
        stats["bookings_total"] = 0.0
        stats["sales_cash"] = 0.0
        stats["sales_terminal"] = 0.0
        stats["sales_qr"] = 0.0
        stats["sales_installment"] = 0.0
    return stats

def increment_preorder(cash=0.0, terminal=0.0, qr=0.0, installment=0.0):
    stats = load_stats()
    stats = check_and_reset(stats)
    stats["preorders"] += 1
    stats["preorders_cash"] += cash
    stats["preorders_terminal"] += terminal
    stats["preorders_qr"] += qr
    stats["preorders_installment"] += installment
    save_stats(stats)

def increment_booking(amount=0.0):
    stats = load_stats()
    stats = check_and_reset(stats)
    stats["bookings"] += 1
    stats["bookings_total"] += amount
    save_stats(stats)

def increment_sales(count=1, cash=0.0, terminal=0.0, qr=0.0, installment=0.0):
    stats = load_stats()
    stats = check_and_reset(stats)
    stats["sales"] += count
    stats["sales_cash"] += cash
    stats["sales_terminal"] += terminal
    stats["sales_qr"] += qr
    stats["sales_installment"] += installment
    save_stats(stats)

def get_stats():
    stats = load_stats()
    stats = check_and_reset(stats)
    return stats

def reset_stats():
    stats = load_stats()
    stats = check_and_reset(stats)
    stats["preorders"] = 0
    stats["bookings"] = 0
    stats["sales"] = 0
    stats["preorders_cash"] = 0.0
    stats["preorders_terminal"] = 0.0
    stats["preorders_qr"] = 0.0
    stats["preorders_installment"] = 0.0
    stats["bookings_total"] = 0.0
    stats["sales_cash"] = 0.0
    stats["sales_terminal"] = 0.0
    stats["sales_qr"] = 0.0
    stats["sales_installment"] = 0.0
    save_stats(stats)

def reset_finances():
    stats = load_stats()
    stats = check_and_reset(stats)
    stats["preorders_cash"] = 0.0
    stats["preorders_terminal"] = 0.0
    stats["preorders_qr"] = 0.0
    stats["preorders_installment"] = 0.0
    stats["bookings_total"] = 0.0
    stats["sales_cash"] = 0.0
    stats["sales_terminal"] = 0.0
    stats["sales_qr"] = 0.0
    stats["sales_installment"] = 0.0
    save_stats(stats)
