#!/bin/sh
set -e

echo "🔥 Проверяем окружение..."
if [ -z "$DATABASE_URL" ]; then
    echo "❌ FATAL: DATABASE_URL is not set!"
    exit 1
fi

if [ -z "$BOT_TOKEN" ]; then
    echo "❌ FATAL: BOT_TOKEN is not set!"
    exit 1
fi

echo "✅ Переменные окружения в порядке."

echo "🔄 Применяем миграции Alembic..."
python run_migrations.py

echo "🚀 Запускаем основной сервер..."
exec python main.py
