#!/usr/bin/env python
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from alembic import command
from alembic.config import Config

sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL не задан", file=sys.stderr)
    sys.exit(1)

alembic_ini_path = Path(__file__).parent / "alembic.ini"
if not alembic_ini_path.exists():
    print("❌ alembic.ini не найден", file=sys.stderr)
    sys.exit(1)

alembic_cfg = Config(str(alembic_ini_path))
alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

print("🔄 Применяем миграции Alembic...")
try:
    command.upgrade(alembic_cfg, "head")
    print("✅ Миграции успешно применены.")
except Exception as e:
    print(f"❌ Ошибка миграций: {e}", file=sys.stderr)
    sys.exit(1)
