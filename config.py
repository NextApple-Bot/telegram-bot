import os

# Токен бота (обязательно)
TOKEN = os.environ.get("BOT_TOKEN")

# ID администратора (обязательно)
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

# ID группы, где работает бот (обязательно)
MAIN_GROUP_ID = int(os.environ.get("MAIN_GROUP_ID", 0))

# ID топиков (обязательные для соответствующих функций)
THREAD_SALES = int(os.environ.get("THREAD_SALES", 0))          # топик продаж
THREAD_ASSORTMENT = int(os.environ.get("THREAD_ASSORTMENT", 0)) # топик загрузки ассортимента
THREAD_ARRIVAL = int(os.environ.get("THREAD_ARRIVAL", 0))      # топик прибытия новых товаров

# ID топика для предзаказов (необязательный, по умолчанию 0 – обработчик не сработает)
THREAD_PREORDER = int(os.environ.get("THREAD_PREORDER", 0))

# Файл для хранения инвентаря
INVENTORY_FILE = "inventory.json"

# Папка для резервных копий
BACKUP_DIR = "backups"
MAX_BACKUPS = 10

# Проверка обязательных переменных (без THREAD_PREORDER, так как он опционален)
if not TOKEN or not ADMIN_ID or not MAIN_GROUP_ID or not THREAD_SALES or not THREAD_ASSORTMENT:
    raise ValueError("Не заданы обязательные переменные окружения: BOT_TOKEN, ADMIN_ID, MAIN_GROUP_ID, THREAD_SALES, THREAD_ASSORTMENT")
