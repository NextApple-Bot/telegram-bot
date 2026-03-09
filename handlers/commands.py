from aiogram import F
from aiogram.types import Message
from aiogram.filters import Command
import csv
import tempfile
import os
import aiosqlite
from aiogram.types import FSInputFile

from .base import (
    router, logger, show_inventory, cancel_action, get_main_menu_keyboard, show_help
)
import config
from database import DB_PATH

@router.message(Command("start"))
async def cmd_start(message: Message, bot):
    logger.info(f"🔥 Команда /start получена от {message.from_user.id}")
    try:
        keyboard = get_main_menu_keyboard()
        await message.answer(
            "👋 Добро пожаловать! Используйте кнопки ниже для управления.",
            reply_markup=keyboard
        )
        logger.info(f"✅ Ответ на /start отправлен пользователю {message.from_user.id}")
    except Exception as e:
        logger.exception(f"❌ Ошибка при обработке /start: {e}")

@router.message(Command("inventory"))
async def cmd_inventory(message: Message, bot):
    await show_inventory(bot, message.chat.id)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot, state):
    await cancel_action(bot, message.chat.id, state)
    await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())

@router.message(Command("help"))
async def cmd_help(message: Message, bot):
    await show_help(bot, message.chat.id)

@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message, bot):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID', 'ФИО', 'Телефон', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации'])

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM clients ORDER BY id')
            rows = await cursor.fetchall()
            for row in rows:
                writer.writerow([
                    row['id'],
                    row['full_name'],
                    row['phone'],
                    row['telegram_username'],
                    row['social_network'],
                    row['referral_source'],
                    row['created_at']
                ])

        tmp_path = tmp.name

    try:
        await message.answer_document(
            FSInputFile(tmp_path, filename="clients.csv"),
            caption="📁 Экспорт клиентов"
        )
    finally:
        os.unlink(tmp_path)
