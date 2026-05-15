#!/bin/sh
set -e

echo "🚀 Запуск Telegram Bot + Admin Panel..."

# Выполняем миграции
echo "📦 Применяем миграции Alembic..."
python run_migrations.py

# Запускаем приложение
echo "🌐 Запуск uvicorn..."
exec uvicorn main:main_entry --host 0.0.0.0 --port ${PORT:-8000} --workers 2
