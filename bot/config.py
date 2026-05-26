from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    BOT_TOKEN: str = ""
    ADMIN_IDS_STR: str = Field(default="", alias="ADMIN_IDS")
    MAIN_GROUP_ID: int = 0

    # Threads (Topics)
    THREAD_ARRIVAL: int = 0
    THREAD_SALES: int = 0
    THREAD_PREORDER: int = 0
    THREAD_ASSORTMENT: int = 0
    THREAD_SERVICE: int = 0

    # Webhook
    USE_WEBHOOK: bool = False
    WEBHOOK_URL: str = ""
    WEBHOOK_SECRET: str = ""

    # Render
    RENDER_URL: str = ""
    RENDER_EXTERNAL_URL: str = ""

    # Database
    DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 20
    DB_POOL_MAX_OVERFLOW: int = 10

    # Admin
    ADMIN_PASSWORD_HASH: str = ""
    ADMIN_PASSWORD: str = ""

    # Debug
    DEBUG: bool = False

    # Other
    SECRET_KEY: str = ""
    PLAN_AMOUNT: int = 0

    @property
    def ADMIN_IDS(self) -> list[int]:
        if not self.ADMIN_IDS_STR:
            return []
        try:
            return [int(x.strip()) for x in self.ADMIN_IDS_STR.split(",") if x.strip()]
        except Exception:
            return []


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
config = settings
