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

import config
import inventory
import stats
from sort_assortment import sort_assortment_to_categories, build_output_text

logger = logging.getLogger(__name__)

router = Router()

async def show_inventory(bot: Bot, chat_id: int) -> Message | None:
    """
    Отправляет файл с текущим ассортиментом в указанный чат.
    Возвращает отправленное сообщение или None.
    """
    categories = await inventory.load_inventory()
    if not categories:
        return await bot.send_message(chat_id, "📭 Ассортимент пуст.")
    text = build_output_text(categories)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp_path = f.name
    try:
        document = FSInputFile(tmp_path, filename="assortiment.txt")
        msg = await bot.send_document(
            chat_id,
            document,
            caption=f"📦 Текущий ассортимент (категорий: {len(categories)})"
        )
        return msg
    finally:
        os.unlink(tmp_path)

async def show_help(bot: Bot, chat_id: int):
    """Отправляет справочное сообщение со списком команд."""
    help_text = """
👋 **Справка по командам бота**

**Основные команды:**
• /start – показать главное меню
• /inventory – выгрузить файл с ассортиментом
• /cancel – отменить текущее действие
• /help – эта справка

**Экспорт данных (только для админа):**
• /export_clients – выгрузить всех клиентов в CSV
• /export_purchases – выгрузить все покупки в CSV
• /export_full_report – полный отчёт (клиенты + покупки)
• /client_info <телефон/имя> – информация о клиенте

**Управление категориями (админ):**
• /show_categories – список категорий с ID
• /clean_empty – удалить все пустые категории
• /delete_category <ID> – удалить пустую категорию
• /merge_categories <from_id> <to_id> – объединить категории (перенести товары)

**Управление данными (админ):**
• /reset_assortment – полностью очистить ассортимент
• /delete_client <ID> – удалить клиента и его покупки
• /delete_purchase <ID> – удалить конкретную покупку
• /migrate – выполнить миграцию БД (однократно)

**Кнопки в меню:**
• «Показать ассортимент» – аналог /inventory
• «Статистика» – продажи/брони за сегодня
• «Финансы» – суммы за сегодня
• «Выгрузить ассортимент» – отправить ассортимент в топик
• «Остатки» – остатки товаров (без брони и Б/У/NS)
• «Клиенты по месяцам» – скачать данные за месяц

Если нужна помощь по конкретной команде, просто введите её.
"""
    await bot.send_message(chat_id, help_text, parse_mode='Markdown')

async def cancel_action(bot: Bot, chat_id: int, state: FSMContext):
    """Отменяет текущее состояние FSM и отправляет подтверждение."""
    await state.clear()
    await bot.send_message(chat_id, "✅ Действие отменено.")

def get_main_menu_keyboard():
    """Возвращает inline-клавиатуру главного меню."""
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
            InlineKeyboardButton(text="📦 Остатки", callback_data="menu:remains"),
            InlineKeyboardButton(text="📅 Клиенты по месяцам", callback_data="menu:clients_by_month"),
        ],
        [
            InlineKeyboardButton(text="🗑️ Очистить ассортимент", callback_data="menu:clear"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel"),
        ]
    ])

__all__ = [
    'router',
    'show_inventory',
    'show_help',
    'cancel_action',
    'get_main_menu_keyboard'
]
