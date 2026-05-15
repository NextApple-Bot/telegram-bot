from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # Telegram
    BOT_TOKEN: str
    ADMIN_IDS: List[int] = []
    ADMIN_IDS_STR: str = ''
    MAIN_GROUP_ID: int | None = None

    # Database
    DATABASE_URL: str
    DB_POOL_SIZE: int = 20
    DB_POOL_MAX_OVERFLOW: int = 10
    DEBUG: bool = False

    # Redis
    REDIS_URL: str = 'redis://localhost:6379/0'
    USE_REDIS_STORAGE: bool = True

    # Web & Security
    SECRET_KEY: str
    ADMIN_PASSWORD_HASH: Optional[str] = None
    RENDER_URL: str = ''

    # Monitoring
    SENTRY_DSN: Optional[str] = None
    ENVIRONMENT: str = 'production'

    # Business
    PLAN_AMOUNT: int = 600000

    @model_validator(mode='before')
    @classmethod
    def parse_admin_ids(cls, data):
        if isinstance(data, dict):
            admin_str = data.get('ADMIN_IDS_STR', '') or data.get('ADMIN_ID', '')
            if admin_str:
                try:
                    data['ADMIN_IDS'] = [int(x.strip()) for x in str(admin_str).split(',') if x.strip()]
                except ValueError:
                    data['ADMIN_IDS'] = []
            else:
                data['ADMIN_IDS'] = []
        return data

    @field_validator('SECRET_KEY')
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError('SECRET_KEY must be at least 32 characters long for security')
        return v

    @field_validator('BOT_TOKEN')
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if not v or len(v) < 30:
            raise ValueError('Invalid BOT_TOKEN')
        return v

settings = Settings()