import os

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
MAIN_GROUP_ID = int(os.environ.get("MAIN_GROUP_ID", 0))
THREAD_SALES = int(os.environ.get("THREAD_SALES", 0))
THREAD_ASSORTMENT = int(os.environ.get("THREAD_ASSORTMENT", 0))
THREAD_ARRIVAL = int(os.environ.get("THREAD_ARRIVAL", 0))

INVENTORY_FILE = "inventory.json"
BACKUP_DIR = "backups"
MAX_BACKUPS = 10

if not TOKEN or not ADMIN_ID or not MAIN_GROUP_ID or not THREAD_SALES or not THREAD_ASSORTMENT:
    raise ValueError("Не заданы обязательные переменные окружения")
