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

# Устанавливаем PYTHONPATH для импорта модулей при необходимости
export PYTHONPATH=/app

echo "🔄 Проверяем, существует ли уже таблица 'clients'..."
python -c "
import asyncio
import asyncpg
import os
import sys

async def check_and_stamp():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    try:
        # Пытаемся сделать запрос к таблице clients
        await conn.execute('SELECT 1 FROM clients LIMIT 1')
        print('✅ Таблица clients уже существует. Пропускаем начальные миграции.')
        sys.exit(0)  # код 0 = таблица есть
    except Exception:
        print('⚠️ Таблица clients не найдена. Будут применены все миграции.')
        sys.exit(1)  # код 1 = таблицы нет
    finally:
        await conn.close()

asyncio.run(check_and_stamp())
"

if [ $? -eq 0 ]; then
    echo "🔄 Помечаем начальные миграции как выполненные..."
    alembic stamp head
fi

echo "🔄 Применяем оставшиеся миграции Alembic..."
python run_migrations.py

echo "🚀 Запускаем основной сервер..."
exec python main.py
