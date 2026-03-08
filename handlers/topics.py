import re
import tempfile
import os
import aiofiles
from datetime import datetime
from aiogram import F, Bot
from aiogram.types import Message, ReactionTypeEmoji, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

import config
import inventory
import stats
from database import add_item, get_item_id_by_serial, add_booking, add_preorder, add_sale
from .base import (
    router, logger, AssortmentConfirmState, ArrivalConfirmState,
    add_item_to_categories, sort_assortment_to_categories, build_output_text, get_main_menu_keyboard
)

# ====== Вспомогательные функции для извлечения сумм ======
def extract_all_amounts(text):
    """Извлекает из текста все упоминания сумм с ключевыми словами."""
    patterns = [
        (r'Наличные|Наличными', 'cash'),
        (r'Терминал', 'terminal'),
        (r'П[\\/]О|ПО', 'prepayment'),
        (r'QR[- ]?код|QR\s*код|QRCode|QrCode|QR\s*Code', 'qr'),
        (r'Рассрочка', 'installment'),
    ]
    results = []
    number_pattern = r'(\d[\d\s]*(?:[.,]\d+)?)'
    for kw, typ in patterns:
        for match in re.finditer(rf'(?:{kw})\s*[-–—]?\s*{number_pattern}', text, re.IGNORECASE):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
                results.append((typ, amount))
            except:
                continue
        for match in re.finditer(rf'{number_pattern}\s*[-–—]?\s*(?:{kw})', text, re.IGNORECASE):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
                results.append((typ, amount))
            except:
                continue
    return results

def extract_preorder_amounts(lines):
    cash = terminal = qr = installment = 0.0
    for line in lines:
        amounts = extract_all_amounts(line)
        for typ, val in amounts:
            if typ == 'cash':
                cash += val
            elif typ == 'terminal':
                terminal += val
            elif typ == 'qr':
                qr += val
            elif typ == 'installment':
                installment += val
    return cash, terminal, qr, installment

def extract_sales_amounts(lines):
    cash = terminal = qr = installment = 0.0
    for line in lines:
        amounts = extract_all_amounts(line)
        for typ, val in amounts:
            if typ == 'prepayment':
                continue
            if typ == 'cash':
                cash += val
            elif typ == 'terminal':
                terminal += val
            elif typ == 'qr':
                qr += val
            elif typ == 'installment':
                installment += val
    return cash, terminal, qr, installment

# -------------------------------------------------------------------
# Топик «Ассортимент» (замена всего)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ASSORTMENT)
async def handle_assortment_upload(message: Message, bot, state):
    logger.info(f"📥 Загрузка ассортимента в топик Ассортимент от {message.from_user.id}")
    # ... (код остаётся без изменений, но использует inventory.save_inventory)
    # Он уже асинхронный, так как save_inventory стал async.
    # Важно: в этом коде вызывается inventory.save_inventory(categories), что корректно.

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
    existing_items = await inventory.get_all_items_with_categories()  # нужно добавить эту функцию в database
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
        # Временное добавление в множества для проверки дубликатов внутри одного сообщения
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
        # Добавляем позиции в БД
        for line in added_lines:
            serial = inventory.extract_serial(line)
            # Определяем категорию. Можно использовать старую функцию add_item_to_categories,
            # но она работала со списком категорий. Для простоты пока добавим в "Общее".
            # Позже можно реализовать логику определения категории.
            await add_item(line, serial, category_name="Общее")

        # Формируем отчёт
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

    # Ищем строки с "Бронь:"
    booking_indices = [i for i, line in enumerate(lines) if re.match(r'^бронь\s*:?$', line.strip().lower())]

    if booking_indices:
        # Предзаказ (до первой брони)
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            cash, terminal, qr, installment = extract_preorder_amounts(preorder_lines)
            await stats.increment_preorder(cash, terminal, qr, installment)
            await message.react([ReactionTypeEmoji(emoji='👌')])

        # Обрабатываем каждую бронь
        for idx in booking_indices:
            start = idx + 1
            end = booking_indices[booking_indices.index(idx) + 1] if booking_indices.index(idx) + 1 < len(booking_indices) else len(lines)
            booking_lines = lines[start:end]
            if not booking_lines:
                await message.reply("❌ Пустой блок брони.")
                continue

            # Ищем строку с серийным номером
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

            # Проверяем, не забронирован ли уже товар
            item_id = await get_item_id_by_serial(serial)
            if not item_id:
                await message.reply(f"❌ Товар с серийным номером {serial} не найден в ассортименте.")
                continue

            # Проверим, есть ли уже бронь на этот товар (по наличию "(Бронь от" в тексте)
            # Для этого нужно получить текст товара по item_id. Добавим функцию в database.
            # Упростим: пока не проверяем, просто удалим товар и добавим с пометкой.
            # Но для этого нужно знать текст товара. Получим его.
            async with aiosqlite.connect(DB_PATH) as db:
                cursor = await db.execute('SELECT text FROM items WHERE id = ?', (item_id,))
                row = await cursor.fetchone()
                if not row:
                    await message.reply(f"❌ Товар с серийным номером {serial} не найден.")
                    continue
                item_text = row[0]

            # Удаляем товар (он будет перемещён в бронь)
            removed = await inventory.remove_by_serial(serial)
            if not removed:
                await message.reply(f"❌ Не удалось удалить товар {serial}.")
                continue

            # Добавляем товар обратно с пометкой о брони
            today = datetime.now().strftime("%d.%m")
            new_item_text = f"{item_text} (Бронь от {today})"
            await add_item(new_item_text, serial, category_name=None)  # категорию можно определить как раньше

            # Считаем сумму брони
            cash, terminal, qr, installment = extract_preorder_amounts(booking_lines)
            total_amount = cash + terminal + qr + installment
            await stats.increment_booking(serial, total_amount)

            await message.react([ReactionTypeEmoji(emoji='👍')])
            await message.reply(f"✅ Добавлена бронь:\n{new_item_text}")

    else:
        # Обычный предзаказ
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
        os.unlink(tmp_path)            elif typ == 'installment':
                installment += val
    return cash, terminal, qr, installment

def extract_sales_amounts(lines):
    cash = 0.0
    terminal = 0.0
    qr = 0.0
    installment = 0.0
    for line in lines:
        amounts = extract_all_amounts(line)
        for typ, val in amounts:
            if typ == 'prepayment':
                continue
            if typ == 'cash':
                cash += val
            elif typ == 'terminal':
                terminal += val
            elif typ == 'qr':
                qr += val
            elif typ == 'installment':
                installment += val
    return cash, terminal, qr, installment

# -------------------------------------------------------------------
# Обработчик для топика «Ассортимент» (с подтверждением)
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
            inventory.save_inventory(categories)
            await callback.message.edit_text("✅ Ассортимент успешно загружен и сохранён.")
        else:
            await callback.message.edit_text("❌ Ошибка: данные не найдены.")
    else:
        await callback.message.edit_text("❌ Загрузка отменена.")
    await state.clear()

# -------------------------------------------------------------------
# Обработчик для топика «Прибытие» (добавление товаров с подтверждением)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ARRIVAL)
async def handle_arrival(message: Message, bot, state):
    logger.info(f"📦 Сообщение в топике Прибытие от {message.from_user.id}")

    # Проверяем, не находится ли пользователь в состоянии подтверждения прибытия
    current_state = await state.get_state()
    if current_state == ArrivalConfirmState.waiting_for_confirm.state:
        await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку.")
        return

    # Парсим входные данные (текст или файл)
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

    # Фильтруем строки, состоящие только из дефисов (разделители)
    lines = [line for line in lines if not re.match(r'^\s*-+\s*$', line)]
    if not lines:
        await message.reply("❌ Нет ни одной позиции после фильтрации.")
        return

    # Загружаем текущий инвентарь
    categories = inventory.load_inventory()
    all_items = inventory.text_only(categories)
    existing_texts = set(all_items)
    existing_serials = {inventory.extract_serial(item) for item in all_items if inventory.extract_serial(item)}

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
        # Пока не добавляем, просто запоминаем
        added_lines.append(line)
        # Обновляем временные множества, чтобы последующие строки в этом же сообщении тоже проверялись на дубликаты между собой
        existing_texts.add(line)
        if serial:
            existing_serials.add(serial)

    if not added_lines:
        await message.reply("❌ Нет новых позиций для добавления (все дубликаты).")
        return

    # Сохраняем временные данные в состояние
    await state.set_state(ArrivalConfirmState.waiting_for_confirm)
    await state.update_data(
        added_lines=added_lines,
        skipped_lines=skipped_lines,
        original_lines=lines,
        message_id=message.message_id,
        chat_id=message.chat.id,
        thread_id=message.message_thread_id
    )

    # Формируем сообщение с подтверждением
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
    original_lines = data.get("original_lines", [])
    # message_id = data.get("message_id") - может пригодиться для логирования

    if action == "yes":
        # Добавляем позиции в инвентарь
        categories = inventory.load_inventory()
        for line in added_lines:
            categories, idx = add_item_to_categories(line, categories)
        inventory.save_inventory(categories)

        # Формируем отчёт
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
    expected_chat_id = data.get("chat_id")
    expected_thread_id = data.get("thread_id")
    if message.chat.id != expected_chat_id or message.message_thread_id != expected_thread_id:
        # Не обрабатываем, если это другой чат/топик
        return
    await state.clear()
    await message.reply("❌ Добавление отменено.")

@router.message(ArrivalConfirmState.waiting_for_confirm)
async def unexpected_message_in_arrival_confirm(message: Message, state):
    data = await state.get_data()
    if message.chat.id == data.get("chat_id") and message.message_thread_id == data.get("thread_id"):
        await message.reply("⚠️ Сначала подтвердите или отмените предыдущую загрузку (используйте кнопки или напишите «отмена»).")
    # else игнорируем

# -------------------------------------------------------------------
# Обработчик для топика «Предзаказ» (брони/предзаказы)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_PREORDER)
async def handle_preorder(message: Message, bot):
    logger.info(f"📥 Сообщение в топике Предзаказ от {message.from_user.id}")

    if not message.text:
        return

    lines = message.text.strip().splitlines()
    if not lines:
        return

    # Находим все индексы строк, начинающихся с "Бронь:"
    booking_indices = []
    for i, line in enumerate(lines):
        if re.match(r'^бронь\s*:?$', line.strip().lower()):
            booking_indices.append(i)

    if booking_indices:
        # Предзаказ: строки до первого "Бронь:"
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            cash, terminal, qr, installment = extract_preorder_amounts(preorder_lines)
            if cash or terminal or qr or installment:
                stats.increment_preorder(cash=cash, terminal=terminal, qr=qr, installment=installment)
            else:
                stats.increment_preorder()
            await message.react([ReactionTypeEmoji(emoji='👌')])

        # Обрабатываем каждую бронь
        for idx in booking_indices:
            start = idx + 1
            end = booking_indices[booking_indices.index(idx) + 1] if booking_indices.index(idx) + 1 < len(booking_indices) else len(lines)
            booking_lines = lines[start:end]
            if not booking_lines:
                await message.reply("❌ Пустой блок брони.")
                continue

            # Ищем строку с серийным номером в этом блоке
            item_line = None
            for line in booking_lines:
                line = line.strip()
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

            # Извлекаем суммы из этого блока
            cash, terminal, qr, installment = extract_preorder_amounts(booking_lines)
            total_amount = cash + terminal + qr + installment

            categories = inventory.load_inventory()

            # Проверка на уже забронированный товар
            booked = False
            for cat in categories:
                for item in cat['items']:
                    if inventory.extract_serial(item) == serial and "(Бронь от" in item:
                        await message.reply(f"⚠️ Товар {serial} уже забронирован.")
                        booked = True
                        break
                if booked:
                    break
            if booked:
                continue

            categories, removed = inventory.remove_by_serial(categories, serial)
            today = datetime.now().strftime("%d.%m")
            new_item = f"{item_line} (Бронь от {today})"
            categories, idx = add_item_to_categories(new_item, categories)
            inventory.save_inventory(categories)

            stats.increment_booking(amount=total_amount)
            await message.react([ReactionTypeEmoji(emoji='👍')])
            await message.reply(f"✅ Добавлена бронь:\n{new_item}")

    else:
        cash, terminal, qr, installment = extract_preorder_amounts(lines)
        if cash or terminal or qr or installment:
            stats.increment_preorder(cash=cash, terminal=terminal, qr=qr, installment=installment)
        else:
            stats.increment_preorder()
        await message.react([ReactionTypeEmoji(emoji='👌')])

# -------------------------------------------------------------------
# Обработчик для топика «Продажи» (удаление по серийным номерам + учёт сумм)
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
    inv = inventory.load_inventory()
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

    if cash or terminal or qr or installment:
        count = len(found_serials) if found_serials else 1
        stats.increment_sales(count=count, cash=cash, terminal=terminal, qr=qr, installment=installment)

    if not_found_serials:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(not_found_serials)
        await message.reply(text)
        logger.info(f"❌ Не найдены: {not_found_serials}")

# -------------------------------------------------------------------
# Функция для выгрузки ассортимента в топик (по кнопке)
# -------------------------------------------------------------------
async def export_assortment_to_topic(bot: Bot, admin_id: int):
    categories = inventory.load_inventory()
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
