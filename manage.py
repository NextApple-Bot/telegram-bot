#!/usr/bin/env python
# Файл: manage.py
import subprocess
import sys
import os
import asyncio
from pathlib import Path

# Добавляем корень проекта в sys.path для импорта bot
sys.path.insert(0, str(Path(__file__).parent))

from bot.db import get_pool, close_pool
from bot.background import cleanup_old_records, cleanup_sold_periodically
from dotenv import load_dotenv
load_dotenv()


def run_migrations():
    """Запускает alembic upgrade head."""
    # Проверяем наличие DATABASE_URL
    if not os.getenv("DATABASE_URL"):
        print("❌ DATABASE_URL не задан в окружении или .env файле.")
        sys.exit(1)
    print("🔄 Запуск миграций...")
    result = subprocess.run(["alembic", "upgrade", "head"])
    if result.returncode == 0:
        print("✅ Миграции успешно выполнены.")
    else:
        print("❌ Ошибка при выполнении миграций.")
        sys.exit(result.returncode)


async def run_cleanup_async():
    """Асинхронный запуск очистки старых записей и проданных товаров."""
    print("🔄 Запуск очистки старых записей...")
    await cleanup_old_records()
    print("🔄 Запуск очистки проданных товаров...")
    await cleanup_sold_periodically()
    await close_pool()
    print("✅ Очистка завершена.")


def run_cleanup():
    """Запускает очистку (синхронная обёртка)."""
    asyncio.run(run_cleanup_async())


def show_help():
    print("Usage: python manage.py [command]")
    print("Commands:")
    print("  migrate   - Run database migrations")
    print("  cleanup   - Run cleanup of old records (processed_messages, daily_payments, sold items)")
    print("  help      - Show this help")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)

    command = sys.argv[1]
    if command == "migrate":
        run_migrations()
    elif command == "cleanup":
        run_cleanup()
    else:
        show_help()
