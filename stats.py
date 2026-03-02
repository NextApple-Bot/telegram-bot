import json
import os
from datetime import datetime

STATS_FILE = "stats.json"

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        return {"date": None, "preorders": 0, "bookings": 0, "sales": 0}

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
    return stats

def add_preorder(delta=1):
    stats = load_stats()
    stats = check_and_reset(stats)
    stats["preorders"] += delta
    save_stats(stats)

def add_booking(delta=1):
    stats = load_stats()
    stats = check_and_reset(stats)
    stats["bookings"] += delta
    save_stats(stats)

def add_sales(delta=1):
    stats = load_stats()
    stats = check_and_reset(stats)
    stats["sales"] += delta
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
    save_stats(stats)
