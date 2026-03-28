from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from bot import config
from bot.services.assortment import AssortmentService
from bot.repositories import StatsRepository, ClientRepository, ItemRepository
from bot.db import get_pool
from bot.utils.sort import get_full_model_name, detect_sim_type
from bot.utils.markdown import escape_markdown_v1
from .base import router, logger, show_inventory, show_help, cancel_action, get_main_menu_keyboard
from .topics.common import export_assortment_to_topic

import json
import csv
import tempfile
import os
from datetime import datetime
from aiogram.types import FSInputFile

# Словари для хранения ID последних сообщений (чтобы удалять старые)
last_stats_message = {}
last_inventory_message = {}
last_remains_message = {}
last_clients_month_message = {}

async def safe_delete(message):
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

@router.callback_query(F.data == "menu:remains")
async def process_remains(callback: CallbackQuery):
    """Обработчик кнопки «Остатки»"""
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

@router.callback_query(F.data.startswith("month:"))
async def process_month_selection(callback: CallbackQuery):
    """Обработчик выбора месяца для отчёта по клиентам"""
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    month = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    if chat_id in last_clients_month_message:
        try:
            await callback.bot.delete_message(chat_id, last_clients_month_message[chat_id])
        except Exception as e:
            logger.warning(f"Не удалось удалить старое сообщение отчёта: {e}")

    await callback.message.edit_text(f"⏳ Формирую отчёт за {month}...")

    try:
        rows = await ClientRepository.get_clients_data_for_month(month)

        if not rows:
            await safe_delete(callback.message)
            await callback.message.answer("📭 Нет данных за этот месяц.")
            keyboard = get_main_menu_keyboard()
            await callback.message.answer("Выберите действие:", reply_markup=keyboard)
            return

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
            writer = csv.writer(tmp)
            writer.writerow([
                'ID клиента', 'ФИО', 'Телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник',
                'Дата регистрации клиента',
                'ID покупки', 'Дата покупки', 'Товары', 'Сумма', 'Способ оплаты (JSON)', 'Тип покупки'
            ])

            for row in rows:
                items_text = ''
                if row['items_json']:
                    try:
                        items = json.loads(row['items_json'])
                        items_text = '; '.join([f"{it.get('item_text', '')[:50]} ({it.get('price', '')}₽)" for it in items])
                    except:
                        items_text = row['items_json']

                writer.writerow([
                    row['client_id'],
                    row['full_name'],
                    row['phone'],
                    row['phones'],
                    row['telegram_username'],
                    row['social_network'],
                    row['referral_source'],
                    row['client_created_at'],
                    row['purchase_id'],
                    row['purchase_created_at'],
                    items_text,
                    row['total_amount'],
                    row['payment_details'],
                    row['purchase_type']
                ])

            tmp_path = tmp.name

        await safe_delete(callback.message)

        sent = await callback.message.answer_document(
            FSInputFile(tmp_path, filename=f"clients_{month}.csv"),
            caption=f"📁 Данные клиентов за {month}"
        )
        last_clients_month_message[chat_id] = sent.message_id

        os.unlink(tmp_path)

        keyboard = get_main_menu_keyboard()
        await callback.message.answer("Выберите действие:", reply_markup=keyboard)

    except Exception as e:
        logger.exception(f"Ошибка при формировании отчёта за {month}")
        await safe_delete(callback.message)
        await callback.message.answer("❌ Произошла ошибка при формировании отчёта.")
        keyboard = get_main_menu_keyboard()
        await callback.message.answer("Выберите действие:", reply_markup=keyboard)

# ---------- Обработчики для подтверждения удаления (категории, ассортимент и т.д.) ----------
@router.callback_query(F.data.startswith("clean_empty:"))
async def process_clean_empty(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    if callback.from_user.id not in config.ADMIN_IDS:
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

    if callback.from_user.id not in config.ADMIN_IDS:
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

    if callback.from_user.id not in config.ADMIN_IDS:
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

    if callback.from_user.id not in config.ADMIN_IDS:
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

    if callback.from_user.id not in config.ADMIN_IDS:
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

    if callback.from_user.id not in config.ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    purchase_id = int(callback.data.split(":")[1])
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM purchases WHERE id = $1', purchase_id)
        await callback.message.edit_text(f"✅ Покупка ID {purchase_id} удалена.")

# ---------- Обработчики сброса статистики ----------
@router.callback_query(F.data.startswith("reset_stats:"))
async def process_reset_stats(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    try:
        if action == "confirm":
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="reset_stats:yes"),
                 InlineKeyboardButton(text="❌ Нет", callback_data="reset_stats:no")]
            ])
            await callback.message.edit_text("Вы уверены, что хотите обнулить статистику?", reply_markup=keyboard)
        elif action == "yes":
            await StatsRepository.reset_today_stats()
            s = await StatsRepository.get_today_stats()
            text = (
                f"📊 Статистика за {s['date']}:\n"
                f"• Предзаказов: {s['preorders_count']}\n"
                f"• Броней: {s['bookings_count']}\n"
                f"• Продаж: {s['sales_count']}"
            )
            await callback.message.edit_text(text)
            last_stats_message[chat_id] = callback.message.message_id
        elif action == "no":
            s = await StatsRepository.get_today_stats()
            text = (
                f"📊 Статистика за {s['date']}:\n"
                f"• Предзаказов: {s['preorders_count']}\n"
                f"• Броней: {s['bookings_count']}\n"
                f"• Продаж: {s['sales_count']}"
            )
            await callback.message.edit_text(text)
            last_stats_message[chat_id] = callback.message.message_id
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    except Exception as e:
        logger.exception(f"Ошибка в process_reset_stats: {e}")
        await callback.message.answer("❌ Произошла ошибка")

@router.callback_query(F.data.startswith("confirm_clear:"))
async def process_confirm_clear(callback: CallbackQuery, bot):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    try:
        if action == "yes":
            await AssortmentService.save_inventory([])
            await StatsRepository.reset_today_stats()
            if chat_id in last_stats_message:
                del last_stats_message[chat_id]
            await callback.message.edit_text("✅ Ассортимент полностью очищен. Статистика сброшена.")
        else:
            await callback.message.edit_text("❌ Очистка отменена.")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())

# -------------------------------------------------------------
# ОСНОВНОЙ ОБРАБОТЧИК МЕНЮ (без финансов)
# -------------------------------------------------------------
@router.callback_query(F.data.startswith("menu:"))
async def process_menu_callback(callback: CallbackQuery, bot, state):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    if action == "inventory":
        if chat_id in last_inventory_message:
            try:
                await bot.delete_message(chat_id, last_inventory_message[chat_id])
            except Exception:
                pass
        msg = await show_inventory(bot, chat_id)
        if msg:
            last_inventory_message[chat_id] = msg.message_id

    elif action == "stats":
        if chat_id in last_stats_message:
            try:
                await bot.delete_message(chat_id, last_stats_message[chat_id])
            except Exception:
                pass
        s = await StatsRepository.get_today_stats()
        text = (
            f"📊 Статистика за {s['date']}:\n"
            f"• Предзаказов: {s['preorders_count']}\n"
            f"• Броней: {s['bookings_count']}\n"
            f"• Продаж: {s['sales_count']}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сбросить статистику", callback_data="reset_stats:confirm")]
        ])
        msg = await callback.message.answer(text, reply_markup=keyboard)
        last_stats_message[chat_id] = msg.message_id

    elif action == "export_assortment":
        await export_assortment_to_topic(bot, user_id)

    elif action == "clients_by_month":
        months = await ClientRepository.get_available_months()
        if not months:
            await callback.message.answer("📭 Нет данных за месяцы.")
            return
        buttons = []
        row = []
        for month in months:
            row.append(InlineKeyboardButton(text=month, callback_data=f"month:{month}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:cancel")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text("📅 Выберите месяц:", reply_markup=keyboard)

    elif action == "remains":
        await process_remains(callback)

    elif action == "clear":
        current_state = await state.get_state()
        if current_state is not None:
            await callback.message.answer("⚠️ Сначала завершите текущее действие (/cancel).")
            return
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, очистить", callback_data="confirm_clear:yes"),
             InlineKeyboardButton(text="❌ Нет, отмена", callback_data="confirm_clear:no")]
        ])
        try:
            await callback.message.edit_text(
                "⚠️ Вы уверены, что хотите полностью очистить ассортимент? Это действие необратимо.",
                reply_markup=keyboard
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise

    elif action == "cancel":
        await cancel_action(bot, chat_id, state)
        try:
            await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu_keyboard())
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise

    elif action == "help":
        await show_help(bot, chat_id)

    else:
        await callback.message.answer("Неизвестная команда")
