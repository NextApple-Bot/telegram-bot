from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Основные настройки бота.
    Все переменные берутся из .env файла.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,          # Игнорируем пустые переменные
    )

    # ==================== Telegram ====================
    BOT_TOKEN: str

    ADMIN_IDS_STR: str = Field(default="", alias="ADMIN_ID")
    ADMIN_IDS: list[int] = Field(default_factory=list)

    MAIN_GROUP_ID: int
    THREAD_SALES: int
    THREAD_ASSORTMENT: int
    THREAD_ARRIVAL: int
    THREAD_PREORDER: int
    THREAD_SERVICE: int = 0

    # ==================== Web & Admin ====================
    RENDER_URL: str = Field(default="", alias="RENDER_EXTERNAL_URL")
    PORT: int = 8000

    # Секретный ключ для сессий (должен быть длинным и случайным)
    SECRET_KEY: str

    # Только bcrypt-хэш пароля администратора (НЕ храните plain-текст!)
    ADMIN_PASSWORD_HASH: str

    # ==================== База данных ====================
    DATABASE_URL: str

    # ==================== Redis ====================
    REDIS_URL: str = "redis://localhost:6379/0"

    # ==================== Бизнес-настройки ====================
    PLAN_AMOUNT: int = 600_000  # план продаж в рублях

    # ==================== Валидаторы ====================

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v, info) -> list[int]:
        """Преобразуем строку ADMIN_IDS_STR в список int."""
        raw = info.data.get("ADMIN_IDS_STR", "")
        if not raw:
            return []
        try:
            return [int(uid.strip()) for uid in raw.split(",") if uid.strip()]
        except ValueError as e:
            raise ValueError(f"Некорректные ADMIN_IDS: {raw}") from e

    @model_validator(mode="after")
    def validate_secrets(self):
        """Проверяем критически важные секреты."""
        if len(self.SECRET_KEY) < 32:
            raise ValueError(
                "SECRET_KEY должен быть минимум 32 символа (рекомендуется 64+)"
            )

        if not self.ADMIN_PASSWORD_HASH or len(self.ADMIN_PASSWORD_HASH) < 20:
            raise ValueError(
                "ADMIN_PASSWORD_HASH обязателен и должен быть bcrypt-хэшем"
            )

        if not self.BOT_TOKEN.startswith("7") or len(self.BOT_TOKEN) < 40:
            raise ValueError("BOT_TOKEN выглядит некорректно")

        return self


# Глобальный экземпляр настроек
config = Settings()
