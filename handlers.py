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

# -------------------------------------------------------------------
# Вспомогательные функции
# -------------------------------------------------------------------
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
    if user_id != config.ADMIN_ID:
        await bot.send_message(target.chat.id, "⛔ У вас нет прав на выполнение этой команды.")
        return
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
        [InlineKeyboardButton(text="📤 Выгрузить ассортимент", callback_data="menu:export_assortment"),
         InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help")],
        [InlineKeyboardButton(text="🗑️ Очистить ассортимент", callback_data="menu:clear"),
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

# -------------------------------------------------------------------
# ВРЕМЕННЫЙ ОБРАБОТЧИК ДЛЯ ПОЛУЧЕНИЯ ID ТОПИКА
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID)
async def debug_thread_id(message: Message):
    logger.info(f"Получено сообщение из топика. Thread ID: {message.message_thread_id}")
    # Если хотите, чтобы бот отвечал в чат, раскомментируйте следующую строку:
    # await message.reply(f"Thread ID этого топика: {message.message_thread_id}")

# -------------------------------------------------------------------
# Команды
# -------------------------------------------------------------------
@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    logger.info(f"🔥 Команда /start получена от {message.from_user.id}")
    try:
        keyboard = get_main_menu_keyboard()
        await message.answer(
            "👋 Добро пожаловать! Используйте кнопки ниже для управления.",
            reply_markup=keyboard
        )
        logger.info(f"✅ Ответ на /start отправлен пользователю {message.from_user.id}")
    except Exception as e:
        logger.exception(f"❌ Ошибка при обработке /start: {e}")

@router.message(Command("inventory"))
async def cmd_inventory(message: Message, bot: Bot):
    await show_inventory(bot, message.chat.id)

@router.message(Command("upload"))
async def cmd_upload(message: Message, bot: Bot, state: FSMContext):
    await start_upload_selection(message, bot, state, message.from_user.id)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot: Bot, state: FSMContext):
    await cancel_action(bot, message.chat.id, state)
    await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())

@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot):
    await show_help(bot, message.chat.id)

@router.message(Command("done"))
async def cmd_done(message: Message, bot: Bot, state: FSMContext):
    current_state = await state.get_state()
    if current_state != UploadStates.waiting_for_inventory.state:
        await message.answer("❌ Сейчас нет накопленных данных для завершения.")
        return
    data = await state.get_data()
    parts = data.get("parts", [])
    mode = data.get("mode")
    if not parts:
        await message.answer("❌ Нет ни одной части для обработки. Отправьте текст или используйте /cancel.")
        return
    full_text = "\n".join(parts)
    await process_full_text(message, full_text, mode, state, bot)

# -------------------------------------------------------------------
# Callback-обработчики
# -------------------------------------------------------------------
@router.callback_query(F.data.startswith("menu:"))
async def process_menu_callback(callback: CallbackQuery, bot: Bot, state: FSMContext):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    await callback.answer()  # немедленный ответ

    if action == "inventory":
        await show_inventory(bot, chat_id)
    elif action == "upload":
        await start_upload_selection(callback.message, bot, state, user_id)
    elif action == "export_assortment":
        if user_id != config.ADMIN_ID:
            await callback.message.answer("⛔ У вас нет прав на выгрузку ассортимента.")
            return
        await export_assortment_to_topic(bot, user_id)
    elif action == "clear":
        if user_id != config.ADMIN_ID:
            await callback.message.answer("⛔ У вас нет прав на это действие.")
            return
        current_state = await state.get_state()
        if current_state is not None:
            await callback.message.answer("⚠️ Сначала завершите текущее действие (/cancel).")
            return
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, очистить", callback_data="confirm_clear:yes"),
             InlineKeyboardButton(text="❌ Нет, отмена", callback_data="confirm_clear:no")]
        ])
        try:
            await callback.message.edit_text(
                "⚠️ Вы уверены, что хотите полностью очистить ассортимент? Это действие необратимо.",
                reply_markup=keyboard
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise
    elif action == "cancel":
        await cancel_action(bot, chat_id, state)
        try:
            await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu_keyboard())
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise
    elif action == "help":
        await show_help(bot, chat_id)
    else:
        await callback.message.answer("Неизвестная команда")

@router.callback_query(F.data.startswith("confirm_clear:"))
async def process_confirm_clear(callback: CallbackQuery, bot: Bot):
    action = callback.data.split(":")[1]
    await callback.answer()

    try:
        if action == "yes":
            inventory.save_inventory([])
            await callback.message.edit_text("✅ Ассортимент полностью очищен.")
        else:
            await callback.message.edit_text("❌ Очистка отменена.")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())

@router.callback_query(UploadStates.waiting_for_mode, F.data.startswith("upload_mode:"))
async def process_mode_selection(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":")[1]
    await callback.answer()

    await state.update_data(mode=mode, parts=[])
    await state.set_state(UploadStates.waiting_for_inventory)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="done:finish")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
    ])
    try:
        await callback.message.edit_text(
            f"Режим: {'🔁 замена' if mode == 'replace' else '➕ добавление'}\n\n"
            "Отправляйте текстовые сообщения с позициями (можно несколько, каждое будет добавлено в буфер).\n"
            "Когда закончите, нажмите кнопку «✅ Готово» или отправьте команду /done.\n"
            "Также можно загрузить готовый текстовый файл .txt (он обработается сразу).\n"
            "Для отмены используйте /cancel или кнопку ниже.",
            reply_markup=keyboard
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            raise

@router.callback_query(UploadStates.waiting_for_inventory, F.data == "done:finish")
async def process_done_callback(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await callback.answer()

    data = await state.get_data()
    parts = data.get("parts", [])
    mode = data.get("mode")
    if not parts:
        await callback.message.answer("❌ Нет накопленных частей. Отправьте текст или загрузите файл.")
        return
    full_text = "\n".join(parts)
    await process_full_text(callback.message, full_text, mode, state, bot)

@router.callback_query(UploadStates.waiting_for_continue, F.data.startswith("continue:"))
async def process_continue(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    await callback.answer()

    if action == "add_more":
        await state.update_data(parts=[])
        await state.set_state(UploadStates.waiting_for_inventory)
        try:
            await callback.message.edit_text(
                "Отправляйте новый список позиций (можно несколько сообщений).\n"
                "Когда закончите, нажмите «✅ Готово» или отправьте /done."
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise
    else:
        await state.clear()
        await callback.message.edit_text("✅ Загрузка завершена. Ассортимент обновлён.")
        await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())

# -------------------------------------------------------------------
# Загрузка текста (накопление) – старый способ
# -------------------------------------------------------------------
@router.message(UploadStates.waiting_for_inventory, F.text)
async def process_inventory_text_part(message: Message, bot: Bot, state: FSMContext):
    if message.from_user.id != config.ADMIN_ID:
        await state.clear()
        return
    data = await state.get_data()
    parts = data.get("parts", [])
    parts.append(message.text.strip())
    await state.update_data(parts=parts)
    await message.react([ReactionTypeEmoji(emoji='👌')])
    await message.answer(f"✅ Часть {len(parts)} принята. Отправьте следующую или нажмите /done / кнопку «✅ Готово».")

@router.message(UploadStates.waiting_for_inventory, F.document)
async def process_inventory_document(message: Message, bot: Bot, state: FSMContext):
    if message.from_user.id != config.ADMIN_ID:
        await state.clear()
        return
    data = await state.get_data()
    mode = data.get("mode")
    document = message.document
    if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
        await message.answer("⚠️ Пожалуйста, отправьте текстовый файл с расширением .txt")
        return
    file_path = f"/tmp/{document.file_name}"
    await bot.download(document, destination=file_path)
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            await message.answer("❌ Файл не содержит позиций. Загрузка отменена.")
            await state.clear()
            return
        current_inventory = inventory.load_inventory()
        if mode == "replace":
            new_objects = inventory.parse_lines_to_objects(lines)
            inventory.save_inventory(new_objects)
            await message.answer(f"✅ Ассортимент полностью заменён из файла. Загружено позиций: {len(new_objects)}")
            await state.clear()
            await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
        else:
            added_count, skipped_lines, new_objects, added_lines = process_new_objects(lines, current_inventory)
            if new_objects:
                updated_inventory = current_inventory + new_objects
                inventory.save_inventory(updated_inventory)
            response = f"✅ Добавлено новых позиций: {added_count}\n⏭ Пропущено (дубликаты): {len(skipped_lines)}\n📦 Всего в ассортименте: {len(current_inventory) + len(new_objects)}\n\n"
            if skipped_lines:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
                    f.write("\n".join(skipped_lines))
                    tmp_path = f.name
                try:
                    doc = FSInputFile(tmp_path, filename="skipped.txt")
                    await message.answer_document(doc, caption=response)
                finally:
                    os.unlink(tmp_path)
            else:
                await message.answer(response)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить ещё", callback_data="continue:add_more"),
                 InlineKeyboardButton(text="✅ Завершить", callback_data="continue:finish")]
            ])
            await message.answer("Хотите добавить ещё позиции?", reply_markup=keyboard)
            await state.set_state(UploadStates.waiting_for_continue)
    except Exception as e:
        await message.answer(f"❌ Ошибка при чтении файла: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

@router.message(UploadStates.waiting_for_inventory)
async def process_inventory_invalid(message: Message):
    await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение или текстовый файл.")

# -------------------------------------------------------------------
# Обработчик для топика «Ассортимент» (с подтверждением)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ASSORTMENT)
async def handle_assortment_upload(message: Message, bot: Bot, state: FSMContext):
    logger.info(f"📥 Загрузка ассортимента в топик Ассортимент от {message.from_user.id}")

    current_state = await state.get_state()
    if current_state == AssortmentConfirmState.waiting_for_confirm.state:
        await state.clear()

    if message.text:
        full_text = message.text.strip()
        if not full_text:
            await message.reply("❌ Пустой список.")
            return
        categories = sort_assortment_to_categories(full_text)
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
    elif message.document:
        document = message.document
        if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
            await message.reply("⚠️ Отправьте текстовый файл .txt")
            return
        file_path = f"/tmp/{document.file_name}"
        await bot.download(document, destination=file_path)
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            if not content.strip():
                await message.reply("❌ Файл пуст.")
                return
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
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        await message.reply("⚠️ Отправьте текст или файл .txt.")

@router.callback_query(AssortmentConfirmState.waiting_for_confirm, F.data.startswith("assort_confirm:"))
async def process_assortment_confirm(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":")[1]
    await callback.answer()

    data = await state.get_data()
    categories = data.get("temp_categories")
    if action == "yes":
        if categories:
            inventory.save_inventory(categories)
            await callback.message.edit_text("✅ Ассортимент успешно загружен и сохранён.")
        else:
            await callback.message.edit_text("❌ Ошибка: данные не найдены.")
    else:
        await callback.message.edit_text("❌ Загрузка отменена.")
    await state.clear()

# -------------------------------------------------------------------
# Обработчик для топика «Прибытие» (добавление товаров)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ARRIVAL)
async def handle_arrival(message: Message, bot: Bot):
    logger.info(f"📦 Сообщение в топике Прибытие от {message.from_user.id}")

    if message.text:
        full_text = message.text.strip()
        if not full_text:
            await message.reply("❌ Пустой список.")
            return
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        if not lines:
            await message.reply("❌ Нет ни одной позиции.")
            return

        categories = inventory.load_inventory()
        all_items = inventory.text_only(categories)
        existing_texts = set(all_items)
        existing_serials = {inventory.extract_serial(item) for item in all_items if inventory.extract_serial(item)}

        added_count = 0
        skipped_lines = []

        for line in lines:
            if line in existing_texts:
                skipped_lines.append(f"[Дубликат текста] {line}")
                continue
            serial = inventory.extract_serial(line)
            if serial and serial in existing_serials:
                skipped_lines.append(f"[Дубликат серийного номера {serial}] {line}")
                continue
            categories, idx = add_item_to_categories(line, categories)
            existing_texts.add(line)
            if serial:
                existing_serials.add(serial)
            added_count += 1

        if added_count > 0:
            inventory.save_inventory(categories)
            await message.react([ReactionTypeEmoji(emoji='✅')])
            await message.reply(f"✅ Добавлено позиций: {added_count}")
        else:
            await message.react([ReactionTypeEmoji(emoji='👎')])
            await message.reply("❌ Ничего не добавлено (все позиции уже есть).")

        if skipped_lines:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write("\n".join(skipped_lines))
                tmp_path = f.name
            try:
                doc = FSInputFile(tmp_path, filename="skipped.txt")
                await message.answer_document(doc, caption=f"⏭ Пропущено: {len(skipped_lines)}")
            finally:
                os.unlink(tmp_path)

    elif message.document:
        document = message.document
        if not (document.mime_type == 'text/plain' or document.file_name.endswith('.txt')):
            await message.reply("⚠️ Отправьте текстовый файл .txt")
            return
        file_path = f"/tmp/{document.file_name}"
        await bot.download(document, destination=file_path)
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            if not lines:
                await message.reply("❌ Файл пуст.")
                return

            categories = inventory.load_inventory()
            all_items = inventory.text_only(categories)
            existing_texts = set(all_items)
            existing_serials = {inventory.extract_serial(item) for item in all_items if inventory.extract_serial(item)}

            added_count = 0
            skipped_lines = []

            for line in lines:
                if line in existing_texts:
                    skipped_lines.append(f"[Дубликат текста] {line}")
                    continue
                serial = inventory.extract_serial(line)
                if serial and serial in existing_serials:
                    skipped_lines.append(f"[Дубликат серийного номера {serial}] {line}")
                    continue
                categories, idx = add_item_to_categories(line, categories)
                existing_texts.add(line)
                if serial:
                    existing_serials.add(serial)
                added_count += 1

            if added_count > 0:
                inventory.save_inventory(categories)
                await message.react([ReactionTypeEmoji(emoji='✅')])
                await message.reply(f"✅ Добавлено позиций: {added_count}")
            else:
                await message.react([ReactionTypeEmoji(emoji='👎')])
                await message.reply("❌ Ничего не добавлено (все позиции уже есть).")

            if skipped_lines:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
                    f.write("\n".join(skipped_lines))
                    tmp_path = f.name
                try:
                    doc = FSInputFile(tmp_path, filename="skipped.txt")
                    await message.answer_document(doc, caption=f"⏭ Пропущено: {len(skipped_lines)}")
                finally:
                    os.unlink(tmp_path)
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        await message.reply("⚠️ Отправьте текст или файл .txt.")

# -------------------------------------------------------------------
# Обработчик для топика «Предзаказ» (брони)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_PREORDER)
async def handle_preorder(message: Message, bot: Bot):
    logger.info(f"📥 Сообщение в топике Предзаказ от {message.from_user.id}")

    if not message.text:
        return

    # Ищем строку, содержащую серийный номер (что-то в скобках длиной ≥5)
    lines = message.text.splitlines()
    item_line = None
    for line in lines:
        line = line.strip()
        if re.search(r'\([A-Z0-9-]{5,}\)', line, re.IGNORECASE):
            item_line = line
            break

    if not item_line:
        await message.reply("❌ Не удалось найти товар с серийным номером.")
        return

    # Добавляем пометку с текущей датой
    today = datetime.now().strftime("%d.%m")  # например, "27.02"
    new_item = f"{item_line} (Бронь от {today})"

    # Сохраняем в инвентарь
    categories = inventory.load_inventory()
    categories, idx = add_item_to_categories(new_item, categories)
    inventory.save_inventory(categories)

    await message.react([ReactionTypeEmoji(emoji='✅')])
    await message.reply(f"✅ Добавлена бронь:\n{new_item}")

# -------------------------------------------------------------------
# Функция для выгрузки ассортимента в топик (по кнопке)
# -------------------------------------------------------------------
async def export_assortment_to_topic(bot: Bot, admin_id: int):
    categories = inventory.load_inventory()
    if not categories:
        await bot.send_message(admin_id, "📭 Ассортимент пуст, нечего выгружать.")
        return
    text = build_output_text(categories)
    today = datetime.now().strftime("%Y%m%d")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        tmp_path = f.name
    try:
        document = FSInputFile(tmp_path, filename=f"assortiment_{today}.txt")
        await bot.send_document(
            chat_id=config.MAIN_GROUP_ID,
            document=document,
            caption=f"📦 Текущий ассортимент (категорий: {len(categories)})",
            message_thread_id=config.THREAD_ASSORTMENT
        )
        await bot.send_message(admin_id, "✅ Ассортимент успешно выгружен в топик «Ассортимент».")
    finally:
        os.unlink(tmp_path)

# -------------------------------------------------------------------
# Обработка сообщений из топика «Продажи» (удаление по серийным номерам)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_SALES)
async def handle_sales_message(message: Message):
    logger.info(f"📩 Сообщение в топике Продажи: {message.text}")
    if not message.text:
        return
    candidates = inventory.extract_serials_from_text(message.text)
    if not candidates:
        return
    inv = inventory.load_inventory()
    found_serials = []
    not_found_serials = []
    for cand in candidates:
        inv, removed = inventory.remove_by_serial(inv, cand)
        if removed:
            found_serials.append(cand)
        else:
            not_found_serials.append(cand)
    if found_serials:
        inventory.save_inventory(inv)
        try:
            await message.react([ReactionTypeEmoji(emoji='🔥')])
        except Exception as e:
            logger.exception(f"Не удалось поставить реакцию: {e}")
    if not_found_serials:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(not_found_serials)
        await message.reply(text)
        logger.info(f"❌ Не найдены: {not_found_serials}")
