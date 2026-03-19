import csv
import json
import tempfile
import os
import logging
from aiogram import Router
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

import config
from bot.db import get_pool
from bot.repositories import ClientRepository, ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.markdown import escape_markdown_v1
from .base import show_inventory, cancel_action, get_main_menu_keyboard, show_help

router = Router()
logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

@router.message(Command("start"))
async def cmd_start(message: Message):
    logger.info(f"🔥 Команда /start получена от {message.from_user.id}")
    try:
        keyboard = get_main_menu_keyboard()
        await message.answer(
            "👋 Добро пожаловать! Используйте кнопки ниже для управления.",
            reply_markup=keyboard
        )
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

# ---------- Экспорт данных ----------
@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    pool = await get
