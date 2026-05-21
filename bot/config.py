from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # ==================== Telegram ====================
    BOT_TOKEN: str = ""
    ADMIN_IDS_STR: str = ""
    MAIN_GROUP_ID: int = 0

    # ==================== Database ====================
    DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 20
    DB_POOL_MAX_OVERFLOW: int = 10

    # ==================== Admin Panel ====================
    ADMIN_PASSWORD_HASH: str = ""

    # ==================== Debug ====================
    DEBUG: bool = False


config = Settings()
