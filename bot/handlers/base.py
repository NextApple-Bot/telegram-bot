import tempfile
import os
import logging
from aiogram import Router, Bot
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.services.assortment import AssortmentService
from bot.utils.sort import build_output_text
from bot.utils.markdown import escape_markdown_v1

logger = logging.getLogger(__name__)

router = Router()

async def show_inventory(bot: Bot, chat_id: int) -> Message | None:
    """
    Отправляет файл с текущим ассортиментом в указанный чат.
    Возвращает отправленное сообщение или None.
    """
    categories = await AssortmentService.load_inventory()
    if not categories:
        return await bot.send_message(chat_id, "📭 Ассортимент пуст.")
    text = build_output_text(categories)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp_path = f.name
    try:
        document = FSInputFile(tmp_path, filename="assortiment.txt")
        msg = await bot.send_document(chat_id, document, caption=f"📦 Текущий ассортимент (категорий: {len(categories)})")
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
• /export\_clients – выгрузить всех клиентов в CSV
• /export\_purchases – выгрузить все покупки в CSV
• /export\_full\_report – полный отчёт (клиенты + покупки)
• /client\_info <телефон/имя> – информация о клиенте

**Управление категориями (админ):**
• /show\_categories – список категорий с ID
• /clean\_empty – удалить все пустые категории
• /delete\_category <ID> – удалить пустую категорию
• /merge\_categories <from\_id> <to\_id> – объединить категории (перенести товары)

**Управление данными (админ):**
• /reset\_assortment – полностью очистить ассортимент
• /delete\_client <ID> – удалить клиента и его покупки
• /delete\_purchase <ID> – удалить конкретную покупку
• /undo – восстановить последний удалённый товар

**Кнопки в меню:**
• «Показать ассортимент» – аналог /inventory
• «Статистика» – продажи/брони за сегодня
• «Финансы» – суммы за сегодня
• «Выгрузить ассортимент» – отправить ассортимент в топик
• «Остатки» – остатки товаров (без брони и Б/У/NS)
• «Клиенты по месяцам» – скачать данные за месяц
"""
    # Экранируем для Markdown (но help_text уже безопасен)
    await bot.send_message(chat_id, help_text, parse_mode='Markdown')

async def cancel_action(bot: Bot, chat_id: int, state: FSMContext):
    """Отменяет текущее состояние FSM и отправляет подтверждение."""
    await state.clear()
    await bot.send_message(chat_id, "✅ Действие отменено.")

def get_main_menu_keyboard():
    """Возвращает inline-клавиатуру главного меню."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Показать ассортимент", callback_data="menu:inventory"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="menu:finance"),
         InlineKeyboardButton(text="📤 Выгрузить ассортимент", callback_data="menu:export_assortment")],
        [InlineKeyboardButton(text="📦 Остатки", callback_data="menu:remains"),
         InlineKeyboardButton(text="📅 Клиенты по месяцам", callback_data="menu:clients_by_month")],
        [InlineKeyboardButton(text="🗑️ Очистить ассортимент", callback_data="menu:clear"),
         InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
    ])
