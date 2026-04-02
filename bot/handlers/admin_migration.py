# Файл: bot/handlers/admin_migration.py
import logging
import os
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from bot import config
from alembic.config import Config
from alembic import command

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("migrate_db"))
async def cmd_migrate_db(message: Message):
    """Выполняет миграцию базы данных до последней версии (только для админов)."""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён")
        return

    # Уведомляем о начале
    status_msg = await message.answer("🔄 Запуск миграции базы данных...")

    try:
        # Путь к файлу alembic.ini (он лежит в корне проекта)
        alembic_cfg = Config("alembic.ini")

        # Устанавливаем URL базы данных из переменной окружения
        alembic_cfg.set_main_option("sqlalchemy.url", config.DATABASE_URL)

        # Выполняем миграцию до head
        command.upgrade(alembic_cfg, "head")

        await status_msg.edit_text("✅ Миграция успешно выполнена!")
        logger.info(f"Админ {message.from_user.id} выполнил миграцию БД")

    except Exception as e:
        error_text = f"❌ Ошибка при выполнении миграции:\n{str(e)}"
        await status_msg.edit_text(error_text)
        logger.exception(f"Ошибка миграции от админа {message.from_user.id}")
