import os
from typing import List

# Обязательные переменные
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
ADMIN_IDS: List[int] = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x] or [ADMIN_ID]  # поддержка нескольких админов
MAIN_GROUP_ID = int(os.environ.get("MAIN_GROUP_ID", 0))
THREAD_SALES = int(os.environ.get("THREAD_SALES", 0))
THREAD_ASSORTMENT = int(os.environ.get("THREAD_ASSORTMENT", 0))
THREAD_ARRIVAL = int(os.environ.get("THREAD_ARRIVAL", 0))
THREAD_PREORDER = int(os.environ.get("THREAD_PREORDER", 0))
DATABASE_URL = os.environ.get("DATABASE_URL")
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 8000))

# План продаж (можно вынести в БД или оставить здесь)
PLAN_AMOUNT = 600000

if not TOKEN or not MAIN_GROUP_ID or not THREAD_SALES or not THREAD_ASSORTMENT:
    raise ValueError("Не заданы обязательные переменные окружения")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан!")
