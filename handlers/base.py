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
from sort_assortment import sort_assortment_to_categories, build_output_text

logger = logging.getLogger(__name__)

router = Router()

class AssortmentConfirmState(StatesGroup):
    waiting_for_confirm = State()

class ArrivalConfirmState(StatesGroup):
    waiting_for_confirm = State()

async def show_inventory(bot: Bot, chat_id: int):
    categories = await inventory.load_inventory()
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
        "/cancel – отменить текущее действие\n\n"
        "В группе бот автоматически отслеживает сообщения в топиках:\n"
        "• Ассортимент – загрузка нового полного списка (с подтверждением)\n"
        "• Прибытие – добавление новых товаров (с подтверждением)\n"
        "• Предзаказ – учёт предзаказов и броней\n"
        "• Продажи – списание товаров по серийным номерам\n\n"
        "При удалении ставит реакцию 🔥, при ненайденном номере пишет сообщение."
    )

async def cancel_action(bot: Bot, chat_id: int, state: FSMContext):
    await state.clear()
    await bot.send_message(chat_id, "✅ Действие отменено.")

def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📦 Показать ассортимент", callback_data="menu:inventory"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats"),
        ],
        [
            InlineKeyboardButton(text="💰 Финансы", callback_data="menu:finance"),
            InlineKeyboardButton(text="📤 Выгрузить ассортимент", callback_data="menu:export_assortment"),
        ],
        [
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
            InlineKeyboardButton(text="🗑️ Очистить ассортимент", callback_data="menu:clear"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel"),
        ]
    ])

__all__ = [
    'router', 'AssortmentConfirmState', 'ArrivalConfirmState',
    'show_inventory', 'show_help', 'cancel_action', 'get_main_menu_keyboard'
]
