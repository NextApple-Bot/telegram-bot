from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    ADMIN_IDS_STR: str = Field(default="", alias="ADMIN_ID")
    ADMIN_IDS: list[int] = []

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

    ADMIN_PASSWORD_HASH: str = ""          # только хэш
    SECRET_KEY: str = ""

    REDIS_URL: str = ""

    @model_validator(mode="after")
    def validate_secrets(self):
        if not self.SECRET_KEY or len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        if not self.ADMIN_PASSWORD_HASH:
            raise ValueError("ADMIN_PASSWORD_HASH must be set")
        return self


config = Settings()
