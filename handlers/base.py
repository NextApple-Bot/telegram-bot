import re
import tempfile
import os
import aiofiles
import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile, Document, CallbackQuery, ReactionTypeEmoji
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

import config
import inventory
import stats
from sort_assortment import sort_assortment_to_categories, build_output_text, add_item_to_categories

logger = logging.getLogger(__name__)
router = Router()

class UploadStates(StatesGroup):
    waiting_for_mode = State()
    waiting_for_inventory = State()
    waiting_for_continue = State()

class AssortmentConfirmState(StatesGroup):
    waiting_for_confirm = State()

class ArrivalConfirmState(StatesGroup):
    waiting_for_confirm = State()

async def show_inventory(bot: Bot, chat_id: int):
    categories = await inventory.load_inventory()   # <-- await
    if not categories:
        await bot.send_message(chat_id, "📭 Ассортимент пуст.")
        return
    text = build_output_text(categories)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp_path = f.name
    try:
        document = FSInputFile(tmp_path, filename="assortiment.txt")
        await bot.send_document(chat_id, document, caption=f"📦 Текущий ассортимент (категорий: {len(categories)})")
    finally:
        os.unlink(tmp_path)

async def show_help(bot: Bot, chat_id: int):
    await bot.send_message(chat_id,
        "👋 Бот для учёта продаж.\n"
        "Команды (можно также использовать кнопки ниже):\n"
        "/inventory – показать текущий ассортимент\n"
        "/upload – загрузить новый ассортимент (замена или добавление)\n"
        "/cancel – отменить текущее действие\n\n"
        "В группе бот автоматически отслеживает сообщения с серийными номерами.\n"
        "При удалении ставит реакцию 🔥, при ненайденном номере пишет сообщение."
    )

async def cancel_action(bot: Bot, chat_id: int, state: FSMContext):
    await state.clear()
    await bot.send_message(chat_id, "✅ Действие отменено.")

async def start_upload_selection(target, bot: Bot, state: FSMContext, user_id: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Заменить весь ассортимент", callback_data="upload_mode:replace"),
         InlineKeyboardButton(text="➕ Добавить к существующему", callback_data="upload_mode:add")]
    ])
    await state.set_state(UploadStates.waiting_for_mode)
    await bot.send_message(target.chat.id, "Выберите режим загрузки:", reply_markup=keyboard)

def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Показать ассортимент", callback_data="menu:inventory"),
         InlineKeyboardButton(text="📤 Загрузить ассортимент", callback_data="menu:upload")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats"),
         InlineKeyboardButton(text="💰 Финансы", callback_data="menu:finance"),
         InlineKeyboardButton(text="📤 Выгрузить ассортимент", callback_data="menu:export_assortment")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
         InlineKeyboardButton(text="🗑️ Очистить ассортимент", callback_data="menu:clear"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
    ])

def process_new_objects(lines, current_inventory):
    # Эта функция больше не используется с SQLite, но оставим для совместимости со старым upload
    # Она синхронная и работает со списком объектов, но мы её не вызываем в новом коде.
    pass

async def process_full_text(message: Message, full_text: str, mode: str, state: FSMContext, bot: Bot):
    # Для загрузки через /upload нужно переписать под SQLite, но пока оставим как есть,
    # т.к. этот функционал может быть не востребован. Рекомендуется позже переделать.
    # Для простоты мы не трогаем upload, но предупреждаем, что он может работать некорректно.
    await message.answer("⚠️ Функция загрузки через /upload временно недоступна. Используйте топик «Ассортимент».")
    await state.clear()

__all__ = [
    'router', 'UploadStates', 'AssortmentConfirmState', 'ArrivalConfirmState',
    'show_inventory', 'show_help', 'cancel_action', 'start_upload_selection',
    'get_main_menu_keyboard', 'process_full_text'
]
