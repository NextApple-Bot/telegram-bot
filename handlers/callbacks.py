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

# Хранилище ID последних сообщений статистики и финансов для каждого чата
last_stats_message = {}
last_finance_message = {}


@router.callback_query(F.data.startswith("menu:"))
async def process_menu_callback(callback: CallbackQuery, bot, state):
    try:
        await callback.answer()
    except Exception as
