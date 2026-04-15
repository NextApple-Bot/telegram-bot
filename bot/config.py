# Файл: bot/config.py
import os
from dotenv import load_dotenv

load_dotenv()

def get_env_var(name: str, required: bool = True) -> str:
    value = os.getenv(name)
    if required and not value:
        raise ValueError(f"❌ Переменная {name} не задана!")
    return value

TOKEN = get_env_var("BOT_TOKEN")
ADMIN_IDS_STR = get_env_var("ADMIN_ID")
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip()]
MAIN_GROUP_ID = int(get_env_var("MAIN_GROUP_ID"))
THREAD_SALES = int(get_env_var("THREAD_SALES"))
THREAD_ASSORTMENT = int(get_env_var("THREAD_ASSORTMENT"))
THREAD_ARRIVAL = int(get_env_var("THREAD_ARRIVAL"))
THREAD_PREORDER = int(get_env_var("THREAD_PREORDER"))

# Служебный топик (может быть 0, если не используется)
THREAD_SERVICE = int(os.getenv("THREAD_SERVICE", "0"))

DATABASE_URL = get_env_var("DATABASE_URL")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", 8000))
PLAN_AMOUNT = int(os.getenv("PLAN_AMOUNT", "600000"))

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
SECRET_KEY = os.getenv("SECRET_KEY")

REDIS_URL = os.getenv("REDIS_URL")
