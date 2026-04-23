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

# Отладка: показываем структуру проекта
echo "📁 Содержимое /app:"
ls -la /app
echo "📁 Содержимое /app/bot:"
ls -la /app/bot || echo "❌ /app/bot не найден"
echo "📁 Содержимое /app/bot/db:"
ls -la /app/bot/db || echo "❌ /app/bot/db не найден"

echo "🔄 Применяем миграции Alembic..."
python run_migrations.py

echo "🚀 Запускаем основной сервер..."
exec python main.py
