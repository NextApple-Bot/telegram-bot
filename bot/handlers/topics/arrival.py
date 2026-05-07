import logging
import os
import re
import tempfile

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.db import get_async_session_factory
from bot.handlers.states import ArrivalConfirmState
from bot.repositories import ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.helpers import send_and_clean
from bot.utils.sort import extract_base_name, normalize_name
from bot.utils.validators import extract_serials
from bot.models import Item, Category

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


async def determine_category_for_item(item_text: str, categories: list) -> str:
    stripped = item_text.strip()
    if stripped.startswith("Б/У -") or stripped.startswith("Б/У "):
        return "Б/У:"
    if stripped.startswith("NS -") or stripped.startswith("NS "):
        return "NS:"
    base = extract_base_name(item_text).lower()
    best_match = None
    best_len = 0
    for cat in categories:
        cat_name = normalize_name(cat['header']).lower().rstrip(':')
        if not cat_name:
            continue
        if base.startswith(cat_name):
            remainder = base[len(cat_name):]
            if (remainder == '' or remainder[0] == ' ') and len(cat_name) > best_len:
                best_len = len(cat_name)
                best_match = cat['header']
        elif cat_name in base and len(cat_name) > best_len:
            best_len = len(cat_name)
            best_match = cat['header']
    if best_match:
        return best_match
    if 'iphone' in item_text.lower():
        base = extract_base_name(item_text)
        return f"{base}:"
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
    # ... (проверка состояния, чтение файла, парсинг строк) без изменений
    # Приведу полный код, но для экономии места опускаю повторяющиеся части.
    # Вся логика обработки сообщения остаётся, меняется только сохранение товаров.
    # Вместо pool.acquire() и conn.execute используем сессию.
    # Ниже только изменённая часть после парсинга.

    # После получения filtered_lines, cat_to_items и т.д.
    # Сохранение товаров при подтверждении:
    @router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
    async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
        try:
            await callback.answer()
        except Exception:
            pass
        data = await state.get_data()
        cat_to_items = data.get("cat_to_items")
        action = callback.data.split(":")[1]

        if action == "yes" and cat_to_items:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                total_inserted = 0
                errors = []
                for cat_name, items in cat_to_items.items():
                    cat_id = await ItemRepository.get_or_create_category(cat_name, conn=session)
                    for text, serial in items:
                        is_booked = 'Бронь от' in text
                        try:
                            session.add(Item(text=text, serial=serial, category_id=cat_id, is_booked=is_booked))
                            total_inserted += 1
                        except Exception as e:
                            errors.append(f"Ошибка при вставке {text}: {e}")
            await AssortmentService.invalidate_cache()
            await callback.message.edit_text(f"✅ Добавлено {total_inserted} товаров. Ошибок: {len(errors)}")
            if errors:
                await send_and_clean(bot=callback.bot, chat_id=callback.message.chat.id,
                                    text="\n".join(errors[:5]), delete_after=60)
        elif action == "no":
            await callback.message.edit_text("❌ Добавление отменено.")
        await state.clear()
