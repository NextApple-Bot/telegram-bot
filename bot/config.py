from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # Telegram
    BOT_TOKEN: str
    ADMIN_IDS_STR: str = ''

    # Telegram Groups / Topics
    MAIN_GROUP_ID: Optional[int] = None
    THREAD_ASSORTMENT: Optional[int] = None
    THREAD_ARRIVAL: Optional[int] = None
    THREAD_PREORDER: Optional[int] = None
    THREAD_SALES: Optional[int] = None
    THREAD_DEPARTURE: Optional[int] = None
    THREAD_SERVICE: Optional[int] = None

    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 10
    DB_POOL_MAX_OVERFLOW: int = 20
    DEBUG: bool = False

    # Redis
    REDIS_URL: str = 'redis://localhost:6379/0'

    # Render / Webhook
    RENDER_URL: Optional[str] = None
    WEBHOOK_BASE_URL: Optional[str] = None

    # Security
    SECRET_KEY: str = "default-insecure-key-for-development-only-change-in-production"
    ADMIN_PASSWORD: str = 'admin'
    ADMIN_PASSWORD_HASH: str = ''   # добавлено для веб-админки

    # Other
    ENVIRONMENT: str = 'development'

    @model_validator(mode='before')
    @classmethod
    def parse_admin_ids(cls, data):
        if isinstance(data, dict):
            admin_str = data.get('ADMIN_IDS_STR', '')
            if admin_str:
                try:
                    data['ADMIN_IDS'] = [int(x.strip()) for x in admin_str.split(',') if x.strip()]
                except ValueError:
                    data['ADMIN_IDS'] = []
            else:
                data['ADMIN_IDS'] = []
        return data

    @field_validator('SECRET_KEY')
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 16 and "default-insecure" in v:
            print("⚠️  WARNING: Using default insecure SECRET_KEY! Change it in production!")
        return v

    @field_validator('BOT_TOKEN')
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if not v or len(v) < 30:
            raise ValueError('Invalid BOT_TOKEN')
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Совместимость
settings = get_settings()
config = settings
