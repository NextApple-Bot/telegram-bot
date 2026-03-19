import os
from dotenv import load_dotenv

load_dotenv()

def get_env_var(name: str, required: bool = True) -> str:
    """Возвращает значение переменной окружения, при необходимости проверяет наличие."""
    value = os.getenv(name)
    if required and not value:
        raise ValueError(f"❌ Переменная окружения {name} не задана!")
    return value

# Админы могут быть перечислены через запятую
ADMIN_IDS_STR = get_env_var("ADMIN_ID")
ADMIN_IDS = [int(id.strip()) for id in ADMIN_IDS_STR.split(",") if id.strip()]
if not ADMIN_IDS:
    raise ValueError("❌ Список ADMIN_ID не может быть пустым!")

TOKEN = get_env_var("BOT_TOKEN")
MAIN_GROUP_ID = int(get_env_var("MAIN_GROUP_ID"))
THREAD_SALES = int(get_env_var("THREAD_SALES"))
THREAD_ASSORTMENT = int(get_env_var("THREAD_ASSORTMENT"))
THREAD_ARRIVAL = int(get_env_var("THREAD_ARRIVAL"))
THREAD_PREORDER = int(get_env_var("THREAD_PREORDER"))
DATABASE_URL = get_env_var("DATABASE_URL")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", 8000))
PLAN_AMOUNT = int(os.getenv("PLAN_AMOUNT", 600000))
