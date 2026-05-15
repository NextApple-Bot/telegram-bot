from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # Telegram
    BOT_TOKEN: str
    ADMIN_IDS_STR: str = ''

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = 'redis://localhost:6379/0'

    # Security
    SECRET_KEY: str
    ADMIN_PASSWORD: str = 'admin'

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