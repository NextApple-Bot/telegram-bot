# Файл: bot/handlers/admin_migration.py
import logging
import os
from pathlib import Path
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
        # Определяем корень проекта (там, где лежит alembic.ini)
        # Пытаемся найти alembic.ini относительно текущего файла
        current_dir = Path(__file__).parent  # bot/handlers
        project_root = current_dir.parent.parent  # поднимаемся на 2 уровня: bot/handlers -> bot -> корень
        alembic_ini_path = project_root / "alembic.ini"

        # Если не нашли, пробуем искать в текущей рабочей директории
        if not alembic_ini_path.exists():
            alembic_ini_path = Path("alembic.ini")

        if not alembic_ini_path.exists():
            await status_msg.edit_text(
                f"❌ Файл alembic.ini не найден. Искали в:\n"
                f"- {project_root / 'alembic.ini'}\n"
                f"- {Path.cwd() / 'alembic.ini'}\n"
                f"Убедитесь, что файл присутствует в корне репозитория."
            )
            logger.error(f"alembic.ini not found in {project_root} or {Path.cwd()}")
            return

        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", config.DATABASE_URL)
        command.upgrade(alembic_cfg, "head")

        await status_msg.edit_text("✅ Миграция успешно выполнена!")
        logger.info(f"Админ {message.from_user.id} выполнил миграцию БД")

    except Exception as e:
        error_text = f"❌ Ошибка при выполнении миграции:\n{str(e)}"
        await status_msg.edit_text(error_text)
        logger.exception(f"Ошибка миграции от админа {message.from_user.id}")
