import json
import os
import fcntl
from datetime import datetime

FINANCES_FILE = "finances.json"

class Finances:
    def __init__(self, file_path=FINANCES_FILE):
        self.file_path = file_path

    def _lock_file(self, f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)

    def _unlock_file(self, f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self._lock_file(f)
                try:
                    data = json.load(f)
                finally:
                    self._unlock_file(f)
            return data
        else:
            return {
                "date": None,
                "terminal": 0,
                "cash": 0,
                "qr": 0,
                "installment": 0,
                "total": 0
            }

    def save(self, data):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            self._lock_file(f)
            try:
                json.dump(data, f, ensure_ascii=False, indent=2)
            finally:
                self._unlock_file(f)

    def check_and_reset(self, data):
        today = datetime.now().strftime("%Y-%m-%d")
        if data["date"] != today:
            data["date"] = today
            data["terminal"] = 0
            data["cash"] = 0
            data["qr"] = 0
            data["installment"] = 0
            data["total"] = 0
        return data

    def add_payment(self, payment_type, amount):
        data = self.load()
        data = self.check_and_reset(data)
        if payment_type in ("terminal", "cash", "qr", "installment"):
            data[payment_type] += amount
            data["total"] += amount
        self.save(data)

    def get(self):
        data = self.load()
        data = self.check_and_reset(data)
        return data

    def reset(self):
        data = self.load()
        data = self.check_and_reset(data)
        data["terminal"] = 0
        data["cash"] = 0
        data["qr"] = 0
        data["installment"] = 0
        data["total"] = 0
        self.save(data)

finances = Finances()
