# Файл: alembic/env.py
import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path
import importlib.util

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# --- Костыль для загрузки Base без пакета ---
# Путь к файлу models.py относительно корня проекта
root_path = Path(__file__).parent.parent
models_path = root_path / "bot" / "db" / "models.py"

spec = importlib.util.spec_from_file_location("bot.db.models", models_path)
models_module = importlib.util.module_from_spec(spec)
sys.modules["bot.db.models"] = models_module
spec.loader.exec_module(models_module)

Base = models_module.Base
# -------------------------------------------

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Получаем URL из переменной окружения
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set")

# Устанавливаем URL в конфиг Alembic
config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
