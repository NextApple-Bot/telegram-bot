import logging
import os
import tempfile

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.handlers.states import AssortmentConfirmState
from bot.repositories.item import ItemRepository
from bot.utils.sort import sort_assortment_to_categories

logger = logging.getLogger(__name__)
router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024

@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ASSORTMENT,
    (F.text | F.caption | F.document)
)
async def handle_assortment_upload(message: Message, bot, state: FSMContext):
    logger.info(f"🔔 ПОЛУЧЕНО СООБЩЕНИЕ В АССОРТИМЕНТ: chat_id={message.chat.id}, thread_id={message.message_thread_id}, "
                f"has_text={bool(message.text)}, has_caption={bool(message.caption)}, has_doc={bool(message.document)}")

    if message.document:
        document = message.document
        logger.info(f"Документ: имя={document.file_name}, размер={document.file_size}, mime={document.mime_type}")
        if document.file_size > MAX_FILE_SIZE:
            await message.reply("❌ Файл слишком большой (макс. 10 МБ).")
            return
        if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
            await message.reply("⚠️ Отправьте текстовый файл .txt")
            return
        # Использование временной директории системы
        with tempfile.NamedTemporaryFile(mode='wb', suffix='_' + document.file_name, delete=False) as tmp:
            file_path = tmp.name
        await bot.download(document, destination=file_path)
        try:
            async with aiofiles.open(file_path, encoding='utf-8') as f:
                content = await f.read()
                if not content.strip():
                    await message.reply("❌ Файл пуст.")
                    return
                categories = sort_assortment_to_categories(content)
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        content = message.text or message.caption
        if not content:
            await message.reply("⚠️ Отправьте текст, файл или фото с подписью.")
            return
        content = content.strip()
        categories = sort_assortment_to_categories(content)

    if not categories:
        await message.reply("❌ Не удалось распознать ни одной категории.")
        return

    await state.update_data(temp_categories=categories)
    await state.set_state(AssortmentConfirmState.waiting_for_confirm)
    total_items = sum(len(cat['items']) for cat in categories)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="assort_confirm:yes"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="assort_confirm:no")]
    ])
    await message.reply(
        f"📦 Найдено категорий: {len(categories)}, всего позиций: {total_items}\n"
        "Подтвердите загрузку (это заменит весь текущий ассортимент).",
        reply_markup=keyboard
    )

# ... остальные функции
