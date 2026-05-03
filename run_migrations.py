#!/usr/bin/env python
# Файл: run_migrations.py
"""Скрипт для запуска миграций Alembic (one-off job на Render)."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from alembic import command

# Исправлено: импорты вынесены в начало
from alembic.config import Config

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL не задан в окружении или .env файле.", file=sys.stderr)
    sys.exit(1)

# Определяем путь к alembic.ini
alembic_ini_path = Path(__file__).parent / "alembic.ini"
if not alembic_ini_path.exists():
    print(f"❌ Файл alembic.ini не найден по пути {alembic_ini_path}", file=sys.stderr)
    sys.exit(1)

alembic_cfg = Config(str(alembic_ini_path))
alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

print("🔄 Запуск миграций...")
try:
    command.upgrade(alembic_cfg, "head")
    print("✅ Миграции успешно выполнены.")
except Exception as e:
    print(f"❌ Ошибка при выполнении миграций: {e}", file=sys.stderr)
    sys.exit(1)
