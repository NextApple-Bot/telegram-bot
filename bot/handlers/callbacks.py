#!/usr/bin/env python
"""
Callback handlers for menu actions.
"""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

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
