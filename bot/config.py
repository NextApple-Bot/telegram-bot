import os
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # --- Основные токены и идентификаторы ---
    BOT_TOKEN: str
    ADMIN_IDS_STR: str = Field(default="", alias="ADMIN_ID")
    ADMIN_IDS: List[int] = []

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v, info):
        raw = info.data.get("ADMIN_IDS_STR", "")
        if not raw:
            return []
        return [int(uid.strip()) for uid in raw.split(",") if uid.strip()]

    MAIN_GROUP_ID: int
    THREAD_SALES: int
    THREAD_ASSORTMENT: int
    THREAD_ARRIVAL: int
    THREAD_PREORDER: int
    THREAD_SERVICE: int = 0

    DATABASE_URL: str
    RENDER_URL: str = Field(default="", alias="RENDER_EXTERNAL_URL")
    PORT: int = 8000
    PLAN_AMOUNT: int = 600000

    ADMIN_PASSWORD: str = ""
    ADMIN_PASSWORD_HASH: str = ""
    SECRET_KEY: str = ""

    REDIS_URL: str = ""


# Загружаем .env для локальной разработки
from dotenv import load_dotenv
load_dotenv()

# Создаём экземпляр конфигурации
config = Settings()

# Экспортируем атрибуты для обратной совместимости
TOKEN = config.BOT_TOKEN
ADMIN_IDS_STR = os.getenv("ADMIN_ID", "")
ADMIN_IDS = config.ADMIN_IDS
MAIN_GROUP_ID = config.MAIN_GROUP_ID
THREAD_SALES = config.THREAD_SALES
THREAD_ASSORTMENT = config.THREAD_ASSORTMENT
THREAD_ARRIVAL = config.THREAD_ARRIVAL
THREAD_PREORDER = config.THREAD_PREORDER
THREAD_SERVICE = config.THREAD_SERVICE
DATABASE_URL = config.DATABASE_URL
RENDER_URL = config.RENDER_URL
PORT = config.PORT
PLAN_AMOUNT = config.PLAN_AMOUNT
ADMIN_PASSWORD = config.ADMIN_PASSWORD
ADMIN_PASSWORD_HASH = config.ADMIN_PASSWORD_HASH
SECRET_KEY = config.SECRET_KEY
REDIS_URL = config.REDIS_URL
