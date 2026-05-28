#!/usr/bin/env python
"""
Callback handlers for menu actions.
"""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.utils.helpers import send_and_clean

from .base import get_main_menu_keyboard, show_inventory, show_help

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "menu:inventory")
async def menu_inventory(callback: CallbackQuery):
    """Показать ассортимент"""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_inventory(callback.bot, callback.message.chat.id)


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery):
    """Показать помощь"""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_help(callback.bot, callback.message.chat.id)


@router.callback_query(F.data == "menu:stats")
async def menu_stats(callback: CallbackQuery):
    """Статистика (временно заглушка)"""
    await callback.answer()
    await callback.message.edit_text(
        "📊 <b>Статистика</b>\n\n"
        "Эта функция пока в разработке.",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu:remains")
async def menu_remains(callback: CallbackQuery):
    """Остатки (временно заглушка)"""
    await callback.answer()
    await callback.message.edit_text(
        "📦 <b>Остатки</b>\n\n"
        "Эта функция пока в разработке.",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu:export_assortment")
async def menu_export_assortment(callback: CallbackQuery):
    """Выгрузить ассортимент (временно заглушка)"""
    await callback.answer()
    await callback.message.edit_text(
        "📤 <b>Выгрузка ассортимента</b>\n\n"
        "Эта функция пока в разработке.",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu:clients_by_month")
async def menu_clients_by_month(callback: CallbackQuery):
    """Клиенты по месяцам (временно заглушка)"""
    await callback.answer()
    await callback.message.edit_text(
        "👥 <b>Клиенты по месяцам</b>\n\n"
        "Эта функция пока в разработке.",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu:clear")
async def menu_clear(callback: CallbackQuery):
    """Очистить ассортимент"""
    await callback.answer()
    await callback.message.edit_text(
        "⚠️ <b>Очистка ассортимента</b>\n\n"
        "Вы уверены, что хотите удалить весь ассортимент?\n\n"
        "Это действие нельзя будет отменить.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да, очистить", callback_data="reset_assortment:confirm")],
            [InlineKeyboardButton(text="Отмена", callback_data="menu:cancel")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu:cancel")
async def process_cancel(callback: CallbackQuery):
    await callback.answer("Отменено")
    try:
        await callback.message.delete()
    except Exception:
        pass

    keyboard = get_main_menu_keyboard()
    await send_and_clean(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        text="Главное меню:",
        reply_markup=keyboard,
        message_thread_id=callback.message.message_thread_id,
        delete_after=60,
    )
