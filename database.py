import re
import tempfile
import os
import aiofiles
import aiosqlite
from datetime import datetime
from aiogram import F, Bot
from aiogram.types import Message, ReactionTypeEmoji, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

import config
import inventory
import stats
from database import add_item, get_item_id_by_serial, add_booking, DB_PATH
from .base import (
    router, logger, AssortmentConfirmState, ArrivalConfirmState,
    sort_assortment_to_categories, build_output_text, get_main_menu_keyboard
)
from utils import extract_preorder_amounts, extract_sales_amounts

# -------------------------------------------------------------------
# Топик «Ассортимент» (замена всего)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ASSORTMENT)
async def handle_assortment_upload(message: Message, bot, state):
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
async def process_assortment_confirm(callback: CallbackQuery, state):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    data = await state.get_data()
    categories = data.get("temp_categories")
    action = callback.data.split(":")[1]
    if action == "yes":
        if categories:
            await inventory.save_inventory(categories)
            await callback.message.edit_text("✅ Ассортимент успешно загружен и сохранён.")
        else:
            await callback.message.edit_text("❌ Ошибка: данные не найдены.")
    else:
        await callback.message.edit_text("❌ Загрузка отменена.")
    await state.clear()

# -------------------------------------------------------------------
# Топик «Прибытие» (добавление товаров с подтверждением)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ARRIVAL)
async def handle_arrival(message: Message, bot, state):
    logger.info(f"📦 Сообщение в топике Прибытие от {message.from_user.id}")

    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку.")
        return

    lines = []
    if message.text:
        full_text = message.text.strip()
        if not full_text:
            await message.reply("❌ Пустой список.")
            return
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
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
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        await message.reply("⚠️ Отправьте текст или файл .txt.")
        return

    lines = [line for line in lines if not re.match(r'^\s*-+\s*$', line)]
    if not lines:
        await message.reply("❌ Нет ни одной позиции после фильтрации.")
        return

    # Получаем существующие товары для проверки дубликатов
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT text, serial FROM items')
        rows = await cursor.fetchall()
        existing_items = [dict(row) for row in rows]
    existing_texts = {item['text'] for item in existing_items}
    existing_serials = {item['serial'] for item in existing_items if item['serial']}

    added_lines = []
    skipped_lines = []

    for line in lines:
        if line in existing_texts:
            skipped_lines.append(f"[Дубликат текста] {line}")
            continue
        serial = inventory.extract_serial(line)
        if serial and serial in existing_serials:
            skipped_lines.append(f"[Дубликат серийного номера {serial}] {line}")
            continue
        added_lines.append(line)
        existing_texts.add(line)
        if serial:
            existing_serials.add(serial)

    if not added_lines:
        await message.reply("❌ Нет новых позиций для добавления (все дубликаты).")
        return

    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(
        added_lines=added_lines,
        skipped_lines=skipped_lines,
        original_lines=lines,
        message_id=message.message_id,
        chat_id=message.chat.id,
        thread_id=message.message_thread_id
    )

    response = f"📦 Найдено новых позиций: {len(added_lines)}\n"
    if skipped_lines:
        response += f"⏭ Пропущено (дубликаты): {len(skipped_lines)}\n"
    response += "Подтвердите добавление?"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="arrival_confirm:yes"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="arrival_confirm:no")]
    ])
    await message.reply(response, reply_markup=keyboard)

@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback: {e}")

    action = callback.data.split(":")[1]
    data = await state.get_data()
    added_lines = data.get("added_lines", [])
    skipped_lines = data.get("skipped_lines", [])

    if action == "yes":
        for line in added_lines:
            serial = inventory.extract_serial(line)
            # Определяем категорию: если строка начинается с "Б/У -" или "Б/У ", отправляем в "Б/У:"
            if line.strip().startswith("Б/У -") or line.strip().startswith("Б/У "):
                category = "Б/У:"
            else:
                category = "Общее:"
            await add_item(line, serial, category_name=category)

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

        today = datetime.now().strftime("%d.%m.%Y")
        filename = f"прибытие_{today}.txt"
        try:
            doc = FSInputFile(tmp_path, filename=filename)
            await callback.message.answer_document(
                doc,
                caption=f"✅ Добавлено: {len(added_lines)} | ⏭ Пропущено: {len(skipped_lines)}"
            )
        finally:
            os.unlink(tmp_path)

        await callback.message.edit_text("✅ Добавление подтверждено.")
    else:
        await callback.message.edit_text("❌ Добавление отменено.")

    await state.clear()

@router.message(ArrivalConfirmState.waiting_for_confirm, F.text.lower() == "отмена")
async def cancel_arrival_confirm_by_text(message: Message, state):
    data = await state.get_data()
    if message.chat.id == data.get("chat_id") and message.message_thread_id == data.get("thread_id"):
        await state.clear()
        await message.reply("❌ Добавление отменено.")

@router.message(ArrivalConfirmState.waiting_for_confirm)
async def unexpected_message_in_arrival_confirm(message: Message, state):
    data = await state.get_data()
    if message.chat.id == data.get("chat_id") and message.message_thread_id == data.get("thread_id"):
        await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки или напишите «отмена»).")

# -------------------------------------------------------------------
# Топик «Предзаказ»
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_PREORDER)
async def handle_preorder(message: Message, bot):
    logger.info(f"📥 Сообщение в топике Предзаказ от {message.from_user.id}")

    if not message.text:
        return

    lines = message.text.strip().splitlines()
    if not lines:
        return

    booking_indices = [i for i, line in enumerate(lines) if re.match(r'^бронь\s*:?$', line.strip().lower())]

    if booking_indices:
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            cash, terminal, qr, installment = extract_preorder_amounts(preorder_lines)
            await stats.increment_preorder(cash, terminal, qr, installment)
            await message.react([ReactionTypeEmoji(emoji='👌')])

        for idx in booking_indices:
            start = idx + 1
            end = booking_indices[booking_indices.index(idx) + 1] if booking_indices.index(idx) + 1 < len(booking_indices) else len(lines)
            booking_lines = lines[start:end]
            if not booking_lines:
                await message.reply("❌ Пустой блок брони.")
                continue

            item_line = None
            for line in booking_lines:
                if re.search(r'\([A-Z0-9-]{5,}\)', line, re.IGNORECASE):
                    item_line = line
                    break

            if not item_line:
                await message.reply("❌ Не удалось найти товар с серийным номером для брони.")
                continue

            serial = inventory.extract_serial(item_line)
            if not serial:
                await message.reply("❌ Не удалось извлечь серийный номер.")
                continue

            item_id = await get_item_id_by_serial(serial)
            if not item_id:
                await message.reply(f"❌ Товар с серийным номером {serial} не найден в ассортименте.")
                continue

            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute('SELECT text FROM items WHERE id = ?', (item_id,))
                row = await cursor.fetchone()
                if not row:
                    await message.reply(f"❌ Товар с серийным номером {serial} не найден.")
                    continue
                item_text = row[0]

            removed = await inventory.remove_by_serial(serial)
            if not removed:
                await message.reply(f"❌ Не удалось удалить товар {serial}.")
                continue

            today = datetime.now().strftime("%d.%m")
            new_item_text = f"{item_text} (Бронь от {today})"
            await add_item(new_item_text, serial, category_name=None)

            cash, terminal, qr, installment = extract_preorder_amounts(booking_lines)
            total_amount = cash + terminal + qr + installment
            await stats.increment_booking(serial, total_amount)

            await message.react([ReactionTypeEmoji(emoji='👍')])
            await message.reply(f"✅ Добавлена бронь:\n{new_item_text}")

    else:
        cash, terminal, qr, installment = extract_preorder_amounts(lines)
        await stats.increment_preorder(cash, terminal, qr, installment)
        await message.react([ReactionTypeEmoji(emoji='👌')])

# -------------------------------------------------------------------
# Топик «Продажи»
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_SALES)
async def handle_sales_message(message: Message):
    logger.info(f"📩 Сообщение в топике Продажи: {message.text}")
    if not message.text:
        return

    lines = message.text.splitlines()
    cash, terminal, qr, installment = extract_sales_amounts(lines)

    candidates = inventory.extract_serials_from_text(message.text)
    found_serials = []
    not_found_serials = []

    for cand in candidates:
        removed = await inventory.remove_by_serial(cand)
        if removed:
            found_serials.append(cand)
        else:
            not_found_serials.append(cand)

    if found_serials:
        try:
            await message.react([ReactionTypeEmoji(emoji='🔥')])
        except Exception as e:
            logger.exception(f"Не удалось поставить реакцию: {e}")

    if cash or terminal or qr or installment:
        count = len(found_serials) if found_serials else 1
        await stats.increment_sales(count=count, cash=cash, terminal=terminal, qr=qr, installment=installment)

    if not_found_serials:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(not_found_serials)
        await message.reply(text)
        logger.info(f"❌ Не найдены: {not_found_serials}")

    # --- СОХРАНЕНИЕ ДАННЫХ КЛИЕНТА ---
    try:
        from client_parser import parse_client_data
        from database import get_or_create_client, add_purchase
        data = parse_client_data(message.text)
        if data['phones'] or data['full_name']:
            client_id = await get_or_create_client(
                phone=data['main_phone'],
                phones=data['phones'],
                full_name=data['full_name'],
                telegram_username=data['telegram_username'],
                social_network=data['social_network'],
                referral_source=data['referral_source']
            )
            await add_purchase(
                client_id=client_id,
                items=data['items'],
                total_amount=data['total'],
                payment_details=data['payments'],
                purchase_type='sale'
            )
            logger.info(f"✅ Сохранены данные клиента {client_id} с покупкой, телефоны: {data['phones']}")
    except Exception as e:
        logger.exception(f"❌ Ошибка при сохранении данных клиента: {e}")

# -------------------------------------------------------------------
# Функция для выгрузки ассортимента в топик
# -------------------------------------------------------------------
async def export_assortment_to_topic(bot: Bot, admin_id: int):
    categories = await inventory.load_inventory()
    if not categories:
        await bot.send_message(admin_id, "📭 Ассортимент пуст, нечего выгружать.")
        return
    text = build_output_text(categories)
    today = datetime.now().strftime("%d.%m.%Y")
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
