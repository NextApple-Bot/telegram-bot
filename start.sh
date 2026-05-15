#!/bin/bash
set -e

echo "🚀 Starting Telegram Bot..."

echo "🔄 Применяем миграции Alembic..."
alembic upgrade head || echo "Миграции пропущены или уже актуальны"

echo "🤖 Запускаем бота..."
exec python main.py