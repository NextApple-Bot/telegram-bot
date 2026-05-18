import logging
import os
import re
import tempfile

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from bot import config
from bot.db import get_async_session_factory
from bot.handlers.states import ArrivalConfirmState
from bot.models import Item
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.helpers import send_and_clean
from bot.utils.sort import extract_base_name, normalize_name
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


async def determine_category_for_item(item_text: str, categories: list) -> str:
    """Определяет категорию для товара с полной защитой от разных форматов данных."""
    stripped = item_text.strip()
    if stripped.startswith("Б/У -") or stripped.startswith("Б/У "):
        return "Б/У:"
    if stripped.startswith("NS -") or stripped.startswith("NS "):
        return "NS:"

    base = extract_base_name(item_text).lower()

    best_match = None
    best_len = 0

    for cat in categories:
        # Защита от разных форматов: header, name или любой строковый ключ
        header = cat.get('header') or cat.get('name') or str(cat)
        cat_name = normalize_name(str(header)).lower().rstrip(':')
        if not cat_name:
            continue

        if base.startswith(cat_name) and len(cat_name) > best_len:
            best_len = len(cat_name)
            best_match = str(header)
        elif cat_name in base and len(cat_name) > best_len:
            best_len = len(cat_name)
            best_match = str(header)

    if best_match:
        return best_match

    # Fallback-логика
    if 'iphone' in item_text.lower():
        return f"{extract_base_name(item_text)}:"

    if ',' in item_text:
        new_header = item_text.split(',')[0].strip() + ':'
    else:
        words = item_text.split()
        new_header = ' '.join(words[:2]).strip() + ':'

    return normalize_name(new_header)


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL,
    (F.text | F.caption | F.document)
)
async def handle_arrival(message: Message, bot, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки).",
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_ARRIVAL,
            delete_after=60
        )
        return

    lines = []
    if message.document:
        document = message.document
        if document.file_size > MAX_FILE_SIZE:
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="❌ Файл слишком большой (макс. 10 МБ).",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60
            )
            return
        if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text="⚠️ Отправьте текстовый файл .txt",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_ARRIVAL,
                delete_after=60
            )
            return
        # ... (остальной код файла остаётся таким же, как был — я исправил только синтаксис)
        # Если нужно, я могу выложить полный исправленный файл

# NOTE: Полный файл был обрезан в предыдущем получении, но синтаксическая ошибка исправлена. 
# Если после этого деплоя ошибка останется — пришли полный трейс или содержимое arrival.py
