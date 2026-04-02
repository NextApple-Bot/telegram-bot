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

    status_msg = await message.answer("🔄 Запуск миграции базы данных...")

    try:
        # Определяем абсолютный путь к alembic.ini (он в корне проекта)
        # Поднимаемся на 3 уровня: bot/handlers -> bot -> корень проекта
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        alembic_ini_path = os.path.join(base_dir, "alembic.ini")

        if not os.path.exists(alembic_ini_path):
            await status_msg.edit_text(f"❌ Файл alembic.ini не найден по пути: {alembic_ini_path}")
            logger.error(f"alembic.ini not found at {alembic_ini_path}")
            return

        alembic_cfg = Config(alembic_ini_path)
        alembic_cfg.set_main_option("sqlalchemy.url", config.DATABASE_URL)
        command.upgrade(alembic_cfg, "head")

        await status_msg.edit_text("✅ Миграция успешно выполнена!")
        logger.info(f"Админ {message.from_user.id} выполнил миграцию БД")

    except Exception as e:
        error_text = f"❌ Ошибка при выполнении миграции:\n{str(e)}"
        await status_msg.edit_text(error_text)
        logger.exception(f"Ошибка миграции от админа {message.from_user.id}")
