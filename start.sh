#!/bin/sh
# set -e   # temporarily disabled for debugging

# ============================================
# start.sh v9 - DEBUG MODE (Background Worker)
# ============================================

echo "🚀 Запуск start.sh v9 - DEBUG MODE"

echo "✅ Проверяем обязательные переменные..."

if [ -z "$DATABASE_URL" ] || [ -z "$BOT_TOKEN" ]; then
    echo "❌ FATAL: DATABASE_URL или BOT_TOKEN не установлены!"
    exit 1
fi

echo "✅ Обязательные переменные в порядке."

echo "🔌 Проверяем подключение к PostgreSQL..."
python -c "
import os, asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    async with engine.connect() as conn:
        await conn.execute(text('SELECT 1'))
    print('✅ Подключение к БД успешно')

asyncio.run(check())
" || echo "⚠️ Ошибка при проверке БД (script continues for debug)"

echo "🔄 Проводим миграции..."
alembic upgrade head || echo "⚠️ Ошибка при миграции (script continues for debug)"
echo "✅ Миграции завершены (or skipped on error)."

echo "🤖 Запускаем Telegram-бота..."
exec python -m bot.bot
