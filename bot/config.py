import os
from dotenv import load_dotenv

load_dotenv()

def get_env_var(name: str, required: bool = True) -> str:
    """Возвращает значение переменной окружения, при необходимости проверяет наличие."""
    value = os.getenv(name)
    if required and not value:
        raise ValueError(f"❌ Переменная {name} не задана!")
    return value

# Обязательные переменные
TOKEN = get_env_var("BOT_TOKEN")

# Администраторы (можно несколько через запятую, пробелы допускаются)
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

# Внешний URL для вебхука (Render предоставляет переменную RENDER_EXTERNAL_URL)
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

# Порт для сервера (Render передаёт PORT)
PORT = int(os.getenv("PORT", 8000))

# План продаж (необязательный)
PLAN_AMOUNT = int(os.getenv("PLAN_AMOUNT", "600000"))

# Админка
ADMIN_PASSWORD = get_env_var("ADMIN_PASSWORD")
SECRET_KEY = get_env_var("SECRET_KEY")

# Хешируем пароль, если он ещё не хеширован (если не начинается с $2b$)
if not ADMIN_PASSWORD.startswith("$2b$"):
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    ADMIN_PASSWORD = pwd_context.hash(ADMIN_PASSWORD)
