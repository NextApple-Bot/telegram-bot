from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

import config
import inventory
import stats
from .base import (
    router, logger, AssortmentConfirmState,
    show_inventory, show_help, cancel_action, get_main_menu_keyboard
)
from .topics import export_assortment_to_topic
from database import get_available_months, get_clients_data_for_month
from sort_assortment import extract_base_name, detect_sim_type  # для остатков
import json
import csv
import tempfile
import os
import asyncpg
from datetime import datetime
from aiogram.types import FSInputFile

last_stats_message = {}
last_finance_message = {}

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
        await show_inventory(bot, chat_id)
    elif action == "stats":
        if chat_id in last_stats_message:
            try:
                await bot.delete_message(chat_id, last_stats_message[chat_id])
            except Exception as e:
                logger.warning(f"Не удалось удалить старое сообщение статистики: {e}")
        s = await stats.get_stats()
        text = (
            f"📊 Статистика за {s['date']}:\n"
            f"• Предзаказов: {s['preorders']}\n"
            f"• Броней: {s['bookings']}\n"
            f"• Продаж: {s['sales']}"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сбросить статистику", callback_data="reset_stats:confirm")]
        ])
        msg = await callback.message.answer(text, reply_markup=keyboard)
        last_stats_message[chat_id] = msg.message_id

    elif action == "finance":
        if chat_id in last_finance_message:
            try:
                await bot.delete_message(chat_id, last_finance_message[chat_id])
            except Exception as e:
                logger.warning(f"Не удалось удалить старое сообщение финансов: {e}")
        s = await stats.get_stats()
        total = (
            s['sales_terminal'] + s['preorders_terminal'] +
            s['sales_cash'] + s['preorders_cash'] +
            s['sales_qr'] + s['preorders_qr'] +
            s['sales_installment'] + s['preorders_installment'] +
            s['bookings_total']
        )
        text = (
            f"💰 Финансы за {s['date']}:\n"
            f"Терминал: {s['sales_terminal'] + s['preorders_terminal']:.0f} руб.\n"
            f"Наличные: {s['sales_cash'] + s['preorders_cash']:.0f} руб.\n"
            f"QR-код: {s['sales_qr'] + s['preorders_qr']:.0f} руб.\n"
            f"Рассрочка: {s['sales_installment'] + s['preorders_installment']:.0f} руб.\n"
            f"ИТОГО: {total:.0f} руб."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сбросить финансы", callback_data="reset_finances:confirm")]
        ])
        msg = await callback.message.answer(text, reply_markup=keyboard)
        last_finance_message[chat_id] = msg.message_id

    elif action == "export_assortment":
        await export_assortment_to_topic(bot, user_id)
    elif action == "clients_by_month":
        if user_id != config.ADMIN_ID:
            await callback.answer("⛔ Доступ запрещён", show_alert=True)
            return
        months = await get_available_months()
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
            await inventory.save_inventory([])
            await stats.reset_stats()
            if chat_id in last_stats_message:
                del last_stats_message[chat_id]
            if chat_id in last_finance_message:
                del last_finance_message[chat_id]
            await callback.message.edit_text("✅ Ассортимент полностью очищен. Статистика и финансы сброшены.")
        else:
            await callback.message.edit_text("❌ Очистка отменена.")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())

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
            await stats.reset_stats()
            s = await stats.get_stats()
            text = (
                f"📊 Статистика за {s['date']}:\n"
                f"• Предзаказов: {s['preorders']}\n"
                f"• Броней: {s['bookings']}\n"
                f"• Продаж: {s['sales']}"
            )
            await callback.message.edit_text(text)
            last_stats_message[chat_id] = callback.message.message_id
        elif action == "no":
            s = await stats.get_stats()
            text = (
                f"📊 Статистика за {s['date']}:\n"
                f"• Предзаказов: {s['preorders']}\n"
                f"• Броней: {s['bookings']}\n"
                f"• Продаж: {s['sales']}"
            )
            await callback.message.edit_text(text)
            last_stats_message[chat_id] = callback.message.message_id
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    except Exception as e:
        logger.exception(f"Ошибка в process_reset_stats: {e}")
        await callback.message.answer("❌ Произошла ошибка")

@router.callback_query(F.data.startswith("reset_finances:"))
async def process_reset_finances(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    try:
        if action == "confirm":
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="reset_finances:yes"),
                 InlineKeyboardButton(text="❌ Нет", callback_data="reset_finances:no")]
            ])
            await callback.message.edit_text("Вы уверены, что хотите обнулить финансовые суммы?", reply_markup=keyboard)
        elif action == "yes":
            await stats.reset_finances()
            s = await stats.get_stats()
            total = (
                s['sales_terminal'] + s['preorders_terminal'] +
                s['sales_cash'] + s['preorders_cash'] +
                s['sales_qr'] + s['preorders_qr'] +
                s['sales_installment'] + s['preorders_installment'] +
                s['bookings_total']
            )
            text = (
                f"💰 Финансы за {s['date']}:\n"
                f"Терминал: {s['sales_terminal'] + s['preorders_terminal']:.0f} руб.\n"
                f"Наличные: {s['sales_cash'] + s['preorders_cash']:.0f} руб.\n"
                f"QR-код: {s['sales_qr'] + s['preorders_qr']:.0f} руб.\n"
                f"Рассрочка: {s['sales_installment'] + s['preorders_installment']:.0f} руб.\n"
                f"ИТОГО: {total:.0f} руб."
            )
            await callback.message.edit_text(text)
            last_finance_message[chat_id] = callback.message.message_id
        elif action == "no":
            s = await stats.get_stats()
            total = (
                s['sales_terminal'] + s['preorders_terminal'] +
                s['sales_cash'] + s['preorders_cash'] +
                s['sales_qr'] + s['preorders_qr'] +
                s['sales_installment'] + s['preorders_installment'] +
                s['bookings_total']
            )
            text = (
                f"💰 Финансы за {s['date']}:\n"
                f"Терминал: {s['sales_terminal'] + s['preorders_terminal']:.0f} руб.\n"
                f"Наличные: {s['sales_cash'] + s['preorders_cash']:.0f} руб.\n"
                f"QR-код: {s['sales_qr'] + s['preorders_qr']:.0f} руб.\n"
                f"Рассрочка: {s['sales_installment'] + s['preorders_installment']:.0f} руб.\n"
                f"ИТОГО: {total:.0f} руб."
            )
            await callback.message.edit_text(text)
            last_finance_message[chat_id] = callback.message.message_id
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    except Exception as e:
        logger.exception(f"Ошибка в process_reset_finances: {e}")
        await callback.message.answer("❌ Произошла ошибка")

# ---------- Обработчик для выбора месяца (клиенты) ----------
@router.callback_query(F.data.startswith("month:"))
async def process_month_selection(callback: CallbackQuery):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    month = callback.data.split(":")[1]
    await callback.message.edit_text(f"⏳ Формирую отчёт за {month}...")

    try:
        rows = await get_clients_data_for_month(month)

        if not rows:
            await callback.message.edit_text(f"📭 Нет данных за {month}.")
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

        await callback.message.answer_document(
            FSInputFile(tmp_path, filename=f"clients_{month}.csv"),
            caption=f"📁 Данные клиентов за {month}"
        )
        os.unlink(tmp_path)

        months = await get_available_months()
        buttons = []
        row = []
        for m in months:
            row.append(InlineKeyboardButton(text=m, callback_data=f"month:{m}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:cancel")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text("📅 Выберите месяц:", reply_markup=keyboard)

    except Exception as e:
        logger.exception(f"Ошибка при формировании отчёта за {month}")
        await callback.message.edit_text("❌ Произошла ошибка при формировании отчёта.")

# ---------- НОВЫЙ ОБРАБОТЧИК ДЛЯ КНОПКИ «ОСТАТКИ» ----------
@router.callback_query(F.data == "menu:remains")
async def process_remains(callback: CallbackQuery):
    try:
        await callback.answer("⏳ Формирую отчёт по остаткам...")
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    # Получаем все товары без брони (регистронезависимо)
    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        rows = await conn.fetch("SELECT text FROM items WHERE text NOT ILIKE '%Бронь от%'")
    finally:
        await conn.close()

    if not rows:
        await callback.message.answer("📭 Нет товаров в наличии.")
        return

    # Группируем товары: ключ = (базовое имя, тип SIM)
    groups = {}
    for row in rows:
        text = row['text']
        base = extract_base_name(text)       # теперь возвращает чистую модель
        sim = detect_sim_type(text)          # определяет тип SIM (eSIM, SIM+eSIM или 'other')
        key = (base, sim)
        groups[key] = groups.get(key, 0) + 1

    # Создаём CSV-файл
    today = datetime.now().strftime("%Y-%m-%d")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['Модель', 'Тип SIM', 'Количество'])
        for (base, sim), count in sorted(groups.items()):
            writer.writerow([base, sim if sim != 'other' else '', count])

        tmp_path = tmp.name

    # Отправляем файл
    await callback.message.answer_document(
        FSInputFile(tmp_path, filename=f"remains_{today}.csv"),
        caption=f"📦 Остатки на {today}"
    )
    os.unlink(tmp_path)
