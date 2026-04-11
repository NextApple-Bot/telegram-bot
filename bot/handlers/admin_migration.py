# Файл: bot/handlers/admin_migration.py
# Команда /migrate_db удалена, так как миграции теперь выполняются через run_migrations.py
import logging
from aiogram import Router
from bot import config

logger = logging.getLogger(__name__)
router = Router()

# В этом файле больше нет обработчиков, оставлен для совместимости импортов
