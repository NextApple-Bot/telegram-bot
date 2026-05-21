#!/bin/sh
set -ex

echo "🚀 Запуск (root start.sh v6 - fixed DB check)..."

required_vars="DATABASE_URL BOT_TOKEN"
for var in $required_vars; do
    if [ -z "$(eval echo \$$var)" ]; then
        echo "❌ FATAL: $var is not set!"
        exit 1
    fi
done

echo "✅ Обязательные переменные в порядке."

# Проверка подключения к БД (fixed for SQLAlchemy 2.0)
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
" || { echo "❌ Не удалось подключиться к БД"; exit 1; }

alembic upgrade head || { echo "⚠️ Ошибка миграций"; exit 1; }
echo "✅ Миграции успешны."

echo "🚀 Запускаем сервер..."
exec python -m uvicorn web_admin.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info
