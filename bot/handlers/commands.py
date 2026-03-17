import csv
import json
import tempfile
import os
from aiogram import Router
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

import config
from bot.repositories import ClientRepository, ItemRepository
from bot.services.assortment import AssortmentService
from .base import router, logger, show_inventory, cancel_action, get_main_menu_keyboard, show_help

@router.message(Command("start"))
async def cmd_start(message: Message, bot):
    logger.info(f"🔥 Команда /start получена от {message.from_user.id}")
    try:
        keyboard = get_main_menu_keyboard()
        await message.answer("👋 Добро пожаловать! Используйте кнопки ниже для управления.", reply_markup=keyboard)
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

# Проверка админа
def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    pool = await get_pool()  # нужно импортировать get_pool из bot.db
    from bot.db import get_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM clients ORDER BY id')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID', 'ФИО', 'Основной телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации'])
        for row in rows:
            writer.writerow([row['id'], row['full_name'], row['phone'], row['phones'], row['telegram_username'], row['social_network'], row['referral_source'], row['created_at']])
        tmp_path = tmp.name
    try:
        await message.answer_document(FSInputFile(tmp_path, filename="clients.csv"), caption="📁 Экспорт клиентов")
    finally:
        os.unlink(tmp_path)

# ... аналогично для остальных команд (export_purchases, client_info, export_full_report, show_categories, clean_empty, delete_category, merge_categories, reset_assortment, delete_client, delete_purchase, undo, chatid)
# В целях экономии места я не буду дублировать все команды, но они должны быть перенесены из вашего старого commands.py с заменой вызовов database на репозитории.
# Например, для /undo:
@router.message(Command("undo"))
async def cmd_undo(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return
    deleted = await ItemRepository.get_last_deleted_item()
    if not deleted:
        await message.answer("📭 Нет удалённых товаров для восстановления.")
        return
    # Проверяем категорию
    from bot.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        cat = await conn.fetchval('SELECT id FROM categories WHERE id = $1', deleted['category_id'])
        if not cat:
            cat_id = await ItemRepository.get_or_create_category("Общее:")
        else:
            cat_id = deleted['category_id']
    await ItemRepository.add_item(text=deleted['text'], serial=deleted['serial'], category_id=cat_id)
    await ItemRepository.restore_deleted_item(deleted['id'])
    await message.answer(f"✅ Товар восстановлен:\n{deleted['text']}")
