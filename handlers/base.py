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

# Состояния для загрузки ассортимента (старый способ)
class UploadStates(StatesGroup):
    waiting_for_mode = State()
    waiting_for_inventory = State()
    waiting_for_continue = State()

class AssortmentConfirmState(StatesGroup):
    waiting_for_confirm = State()

# Вспомогательные функции
async def show_inventory(bot: Bot, chat_id: int):
    categories = inventory.load_inventory()
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
         InlineKeyboardButton(text="💰 Финансы", callback_data="menu:finances")],
        [InlineKeyboardButton(text="📤 Выгрузить ассортимент", callback_data="menu:export_assortment"),
         InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help"),
         InlineKeyboardButton(text="🗑️ Очистить ассортимент", callback_data="menu:clear"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
    ])

def process_new_objects(lines, current_inventory):
    added_count = 0
    skipped_lines = []
    new_objects = []
    added_lines = []
    added_texts_this_batch = set()
    existing_serials = {obj["serial"] for obj in current_inventory if obj["serial"]}
    existing_texts = {obj["text"] for obj in current_inventory}
    for line in lines:
        if line in existing_texts:
            skipped_lines.append(f"[Дубликат текста] {line}")
            continue
        if line in added_texts_this_batch:
            skipped_lines.append(f"[Дубликат в этом же списке] {line}")
            continue
        serial = inventory.extract_serial(line)
        if serial:
            if serial in existing_serials:
                skipped_lines.append(f"[Дубликат серийного номера {serial}] {line}")
                continue
        new_obj = {"text": line, "serial": serial}
        new_objects.append(new_obj)
        added_lines.append(line)
        added_texts_this_batch.add(line)
        existing_texts.add(line)
        if serial:
            existing_serials.add(serial)
        added_count += 1
    return added_count, skipped_lines, new_objects, added_lines

async def process_full_text(message: Message, full_text: str, mode: str, state: FSMContext, bot: Bot):
    lines = [line.strip() for line in full_text.splitlines() if line.strip()]
    if not lines:
        await message.answer("❌ Нет ни одной позиции. Загрузка отменена.")
        await state.clear()
        return
    current_inventory = inventory.load_inventory()
    if mode == "replace":
        new_objects = inventory.parse_lines_to_objects(lines)
        inventory.save_inventory(new_objects)
        await message.answer(f"✅ Ассортимент полностью заменён. Загружено позиций: {len(new_objects)}")
        await state.clear()
        await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
    else:
        added_count, skipped_lines, new_objects, added_lines = process_new_objects(lines, current_inventory)
        if new_objects:
            updated_inventory = current_inventory + new_objects
            inventory.save_inventory(updated_inventory)

        response = f"✅ Добавлено новых позиций: {added_count}\n"
        response += f"⏭ Пропущено (дубликаты): {len(skipped_lines)}\n"
        response += f"📦 Всего в ассортименте: {len(current_inventory) + len(new_objects)}\n\n"
        response += "📄 Подробности в файле result.txt"

        combined_lines = []
        if added_lines:
            combined_lines.append(f"=== ДОБАВЛЕННЫЕ ({len(added_lines)}) ===")
            combined_lines.extend(added_lines)
            combined_lines.append("")
        if skipped_lines:
            combined_lines.append(f"=== ПРОПУЩЕННЫЕ ({len(skipped_lines)}) ===")
            combined_lines.extend(skipped_lines)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("\n".join(combined_lines))
            tmp_path = f.name
        try:
            document = FSInputFile(tmp_path, filename="result.txt")
            await message.answer_document(document, caption=response)
        finally:
            os.unlink(tmp_path)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить ещё", callback_data="continue:add_more"),
             InlineKeyboardButton(text="✅ Завершить", callback_data="continue:finish")]
        ])
        await message.answer("Хотите добавить ещё позиции?", reply_markup=keyboard)
        await state.set_state(UploadStates.waiting_for_continue)

# Экспортируем всё, что нужно в других модулях
__all__ = [
    'router', 'UploadStates', 'AssortmentConfirmState',
    'show_inventory', 'show_help', 'cancel_action', 'start_upload_selection',
    'get_main_menu_keyboard', 'process_new_objects', 'process_full_text'
]
