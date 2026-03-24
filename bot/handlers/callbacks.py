from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from bot import config
from bot.services.assortment import AssortmentService
from bot.repositories import StatsRepository, ClientRepository, ItemRepository, FinanceRepository
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
last_finance_message = {}
last_inventory_message = {}
last_remains_message = {}
last_clients_month_message = {}

# -------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (определены ДО основного обработчика)
# -------------------------------------------------------------

async def safe_delete(message):
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение: {e}")

@router.callback_query(F.data == "menu:remains")
async def process_remains(callback: CallbackQuery):
    # ... (код без изменений) ...
    pass

@router.callback_query(F.data.startswith("month:"))
async def process_month_selection(callback: CallbackQuery):
    # ... (код без изменений) ...
    pass

# ---------- Обработчики для подтверждения удаления (категории, ассортимент и т.д.) ----------
@router.callback_query(F.data.startswith("clean_empty:"))
async def process_clean_empty(callback: CallbackQuery):
    # ... (код без изменений) ...
    pass

@router.callback_query(F.data.startswith("delete_cat:"))
async def process_delete_category(callback: CallbackQuery):
    # ... (код без изменений) ...
    pass

@router.callback_query(F.data.startswith("merge:"))
async def process_merge_categories(callback: CallbackQuery):
    # ... (код без изменений) ...
    pass

@router.callback_query(F.data.startswith("reset_assortment:"))
async def process_reset_assortment(callback: CallbackQuery):
    # ... (код без изменений) ...
    pass

@router.callback_query(F.data.startswith("delete_client:"))
async def process_delete_client(callback: CallbackQuery):
    # ... (код без изменений) ...
    pass

@router.callback_query(F.data.startswith("delete_purchase:"))
async def process_delete_purchase(callback: CallbackQuery):
    # ... (код без изменений) ...
    pass

# ---------- Обработчики сброса статистики и финансов ----------
@router.callback_query(F.data.startswith("reset_stats:"))
async def process_reset_stats(callback: CallbackQuery):
    # ... (код без изменений) ...
    pass

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
            # Удаляем транзакции за сегодня
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute('DELETE FROM transactions WHERE DATE(created_at) = CURRENT_DATE')
            # Обновляем отображение
            fin = await FinanceRepository.get_today()
            stats = await StatsRepository.get_today_stats()
            cash_total = fin['cash']
            terminal_total = fin['terminal']
            qr_total = fin['qr']
            transfer_total = fin['transfer']
            invoice_total = fin['invoice']
            installment_total = fin['installment']
            bookings_total = fin['bookings_total']
            overall_total = fin['total']

            text = (
                f"План - {config.PLAN_AMOUNT}. {stats['sales_count']} продаж.\n"
                f"1) Общая - {overall_total:.0f}" + ("  (План не выполнен)" if overall_total < config.PLAN_AMOUNT else "") + "\n"
                f"2) Наличные - {cash_total:.0f}\n"
                f"3) QR-код - {qr_total:.0f}\n"
                f"4) Рассрочка - {installment_total:.0f}\n"
                f"5) Оплата по счету - {invoice_total:.0f}\n"
                f"6) Терминал - {terminal_total:.0f}\n"
                f"7) Перевод - {transfer_total:.0f}"
            )
            await callback.message.edit_text(text)
            last_finance_message[chat_id] = callback.message.message_id
        elif action == "no":
            fin = await FinanceRepository.get_today()
            stats = await StatsRepository.get_today_stats()
            cash_total = fin['cash']
            terminal_total = fin['terminal']
            qr_total = fin['qr']
            transfer_total = fin['transfer']
            invoice_total = fin['invoice']
            installment_total = fin['installment']
            bookings_total = fin['bookings_total']
            overall_total = fin['total']

            text = (
                f"План - {config.PLAN_AMOUNT}. {stats['sales_count']} продаж.\n"
                f"1) Общая - {overall_total:.0f}" + ("  (План не выполнен)" if overall_total < config.PLAN_AMOUNT else "") + "\n"
                f"2) Наличные - {cash_total:.0f}\n"
                f"3) QR-код - {qr_total:.0f}\n"
                f"4) Рассрочка - {installment_total:.0f}\n"
                f"5) Оплата по счету - {invoice_total:.0f}\n"
                f"6) Терминал - {terminal_total:.0f}\n"
                f"7) Перевод - {transfer_total:.0f}"
            )
            await callback.message.edit_text(text)
            last_finance_message[chat_id] = callback.message.message_id
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    except Exception as e:
        logger.exception(f"Ошибка в process_reset_finances: {e}")
        await callback.message.answer("❌ Произошла ошибка")

@router.callback_query(F.data.startswith("confirm_clear:"))
async def process_confirm_clear(callback: CallbackQuery, bot):
    # ... (код без изменений) ...
    pass

# -------------------------------------------------------------
# ОСНОВНОЙ ОБРАБОТЧИК МЕНЮ
# -------------------------------------------------------------
@router.callback_query(F.data.startswith("menu:"))
async def process_menu_callback(callback: CallbackQuery, bot, state):
    # ... (код без изменений, но убедитесь, что в блоке finance используется `FinanceRepository.get_today()`)
    pass
