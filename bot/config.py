from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ==================== Основные настройки ====================
    BOT_TOKEN: str
    BOT_NAME: str = "NextApple Bot"
    BOT_USERNAME: str = "nextapple_bot"

    # ==================== База данных ====================
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    # ==================== Webhook ====================
    WEBHOOK_BASE_URL: Optional[str] = None          # ← временно optional
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_SECRET: Optional[str] = None

    # ==================== Админ-панель ====================
    ADMIN_USERNAME: Optional[str] = None            # ← временно optional
    ADMIN_PASSWORD: str

    # ==================== Другие настройки ====================
    ENVIRONMENT: str = Field(default="development", alias="ENV")
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = True

    # ==================== Telegram Topics ====================
    TOPICS_ENABLED: bool = True
    SALE_TOPIC_ID: Optional[int] = None
    SUPPORT_TOPIC_ID: Optional[int] = None

    # ==================== Пути ====================
    STATIC_DIR: str = "static"
    TEMPLATES_DIR: str = "web_admin/templates"

    # ==================== Безопасность ====================
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    @property
    def WEBHOOK_URL(self) -> str:
        if not self.WEBHOOK_BASE_URL:
            return ""
        return f"{self.WEBHOOK_BASE_URL}{self.WEBHOOK_PATH}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Ленивая загрузка настроек — теперь ничего не создаётся при импорте модуля"""
    return Settings()


# Для совместимости со всем старым кодом (main.py, alembic, handlers и т.д.)
settings = get_settings()
config = settings
