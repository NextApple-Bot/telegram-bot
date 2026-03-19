import os
from dotenv import load_dotenv

load_dotenv()

def get_env_var(name: str, required: bool = True) -> str:
    value = os.getenv(name)
    if required and not value:
        raise ValueError(f"❌ Переменная {name} не задана!")
    return value

# Обязательные переменные
TOKEN = get_env_var("BOT_TOKEN")

# Администраторы (можно несколько через запятую)
ADMIN_IDS_STR = get_env_var("ADMIN_ID")
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip()]
if not ADMIN_IDS:
    raise ValueError("❌ Список ADMIN_ID не может быть пустым!")

# ID группы и топиков
MAIN_GROUP_ID = int(get_env_var("MAIN_GROUP_ID"))
THREAD_SALES = int(get_env_var("THREAD_SALES"))
THREAD_ASSORTMENT = int(get_env_var("THREAD_ASSORTMENT"))
THREAD_ARRIVAL = int(get_env_var("THREAD_ARRIVAL"))
THREAD_PREORDER = int(get_env_var("THREAD_PREORDER"))

# База данных
DATABASE_URL = get_env_var("DATABASE_URL")

# План продаж (необязательный)
PLAN_AMOUNT = int(os.getenv("PLAN_AMOUNT", "600000"))

# Убираем RENDER_URL и PORT - они больше не нужны
