import json
import csv
import tempfile
import os
from datetime import datetime
from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

import config
import inventory
import stats
from .base import (
    router, logger, show_inventory, show_help, cancel_action, get_main_menu_keyboard
)
from .topics.common import export_assortment_to_topic
from database import (
    get_available_months, get_clients_data_for_month, get_pool  # добавлен get_pool
)
from sort_assortment import extract_base_name, detect_sim_type, get_full_model_name

# ... (словари last_stats_message и др. остаются без изменений)

@router.callback_query(F.data.startswith("menu:"))
async def process_menu_callback(callback: CallbackQuery, bot, state):
    # ... (код без изменений, он не использует прямых connect)
    pass

@router.callback_query(F.data.startswith("month:"))
async def process_month_selection(callback: CallbackQuery):
    # ... (этот хендлер уже использует get_clients_data_for_month, который через пул)
    pass

@router.callback_query(F.data == "menu:remains")
async def process_remains(callback: CallbackQuery):
    try:
        await callback.answer("⏳ Формирую отчёт по остаткам...")
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    chat_id = callback.message.chat.id
    if chat_id in last_remains_message:
        try:
            await callback.bot.delete_message(chat_id, last_remains_message[chat_id])
        except Exception as e:
            logger.warning(f"Не удалось удалить старое сообщение остатков: {e}")

    # Используем пул соединений вместо прямого connect
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT i.text 
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE i.is_booked = false 
              AND c.name NOT IN ('Б/У:', 'Б/У', 'NS:', 'NS')
        ''')

    if not rows:
        await safe_delete(callback.message)
        await callback.message.answer("📭 Нет товаров в наличии.")
        keyboard = get_main_menu_keyboard()
        await callback.message.answer("Выберите действие:", reply_markup=keyboard)
        return

    groups = {}
    for row in rows:
        text = row['text']
        full_name = get_full_model_name(text)
        sim = detect_sim_type(text)
        key = (full_name, sim)
        groups[key] = groups.get(key, 0) + 1

    today = datetime.now().strftime("%Y-%m-%d")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['Модель', 'Тип SIM', 'Количество'])
        for (full_name, sim), count in sorted(groups.items()):
            writer.writerow([full_name, sim if sim != 'other' else '', count])
        tmp_path = tmp.name

    await safe_delete(callback.message)
    sent = await callback.message.answer_document(
        FSInputFile(tmp_path, filename=f"remains_{today}.csv"),
        caption=f"📦 Остатки на {today}"
    )
    last_remains_message[chat_id] = sent.message_id
    os.unlink(tmp_path)
    keyboard = get_main_menu_keyboard()
    await callback.message.answer("Выберите действие:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("clean_empty:"))
async def process_clean_empty(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    action = callback.data.split(":")[1]
    if action != "confirm":
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute('''
            DELETE FROM categories
            WHERE id NOT IN (SELECT DISTINCT category_id FROM items WHERE category_id IS NOT NULL)
        ''')
        deleted = int(result.split()[1]) if result.startswith('DELETE') else 0
        await callback.message.edit_text(f"✅ Удалено пустых категорий: {deleted}")

@router.callback_query(F.data.startswith("delete_cat:"))
async def process_delete_category(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    cat_id = int(callback.data.split(":")[1])
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval('SELECT COUNT(*) FROM items WHERE category_id = $1', cat_id)
        if count > 0:
            await callback.message.edit_text(f"❌ В категории появились товары, удаление отменено.")
            return
        await conn.execute('DELETE FROM categories WHERE id = $1', cat_id)
        await callback.message.edit_text(f"✅ Категория ID {cat_id} удалена.")

@router.callback_query(F.data.startswith("merge:"))
async def process_merge_categories(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    _, from_id, to_id = callback.data.split(':')
    from_id = int(from_id)
    to_id = int(to_id)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('UPDATE items SET category_id = $1 WHERE category_id = $2', to_id, from_id)
            await conn.execute('DELETE FROM categories WHERE id = $1', from_id)
        await callback.message.edit_text(f"✅ Товары перенесены, категория {from_id} удалена.")

@router.callback_query(F.data.startswith("reset_assortment:"))
async def process_reset_assortment(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    action = callback.data.split(":")[1]
    if action != "confirm":
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM categories")
        await callback.message.edit_text("✅ Ассортимент полностью очищен.")

@router.callback_query(F.data.startswith("delete_client:"))
async def process_delete_client(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    client_id = int(callback.data.split(":")[1])
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('DELETE FROM purchases WHERE client_id = $1', client_id)
            await conn.execute('DELETE FROM clients WHERE id = $1', client_id)
        await callback.message.edit_text(f"✅ Клиент ID {client_id} и все его покупки удалены.")

@router.callback_query(F.data.startswith("delete_purchase:"))
async def process_delete_purchase(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    purchase_id = int(callback.data.split(":")[1])
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM purchases WHERE id = $1', purchase_id)
        await callback.message.edit_text(f"✅ Покупка ID {purchase_id} удалена.")

async def safe_delete(message):
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")
