import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
ADMIN_IDS = [ADMIN_ID]  # если понадобится список, можно расширить
MAIN_GROUP_ID = int(os.getenv("MAIN_GROUP_ID", 0))
THREAD_SALES = int(os.getenv("THREAD_SALES", 0))
THREAD_ASSORTMENT = int(os.getenv("THREAD_ASSORTMENT", 0))
THREAD_ARRIVAL = int(os.getenv("THREAD_ARRIVAL", 0))
THREAD_PREORDER = int(os.getenv("THREAD_PREORDER", 0))
DATABASE_URL = os.getenv("DATABASE_URL")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", 8000))
PLAN_AMOUNT = int(os.getenv("PLAN_AMOUNT", 600000))

if not TOKEN or not ADMIN_ID or not MAIN_GROUP_ID or not THREAD_SALES or not THREAD_ASSORTMENT:
    raise ValueError("Не заданы обязательные переменные окружения")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан!")
