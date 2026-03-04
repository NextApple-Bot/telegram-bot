import re
import tempfile
import os
import aiofiles
from datetime import datetime
from aiogram import F, Bot
from aiogram.types import Message, ReactionTypeEmoji, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

import config
import inventory
import stats
from .base import (
    router, logger, AssortmentConfirmState, add_item_to_categories,
    sort_assortment_to_categories, build_output_text, get_main_menu_keyboard
)

def extract_all_amounts(text):
    """
    Извлекает из текста все упоминания сумм с ключевыми словами.
    Возвращает список кортежей (тип_оплаты, сумма).
    Типы: 'cash', 'terminal', 'qr', 'installment'.
    """
    # Ключевые слова и соответствующие типы
    patterns = [
        (r'Наличные|Наличными', 'cash'),
        (r'Терминал', 'terminal'),
        (r'П[\\/]О|ПО', 'prepayment'),  # предоплата (не учитываем в финансах? пока оставим, но потом можно игнорировать)
        (r'QR[- ]?код|QR\s*код|QRCode|QrCode|QR\s*Code', 'qr'),
        (r'Рассрочка', 'installment'),
    ]
    results = []
    # Ищем все числа с возможными пробелами и точкой/запятой
    # Число может быть как целым, так и десятичным (с . или ,)
    number_pattern = r'(\d[\d\s]*(?:[.,]\d+)?)'
    for kw, typ in patterns:
        # Ищем ключевое слово, затем необязательный дефис/тире, затем число
        for match in re.finditer(rf'(?:{kw})\s*[-–—]?\s*{number_pattern}', text, re.IGNORECASE):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
                results.append((typ, amount))
            except:
                continue
        # Ищем число, затем необязательный дефис/тире, затем ключевое слово
        for match in re.finditer(rf'{number_pattern}\s*[-–—]?\s*(?:{kw})', text, re.IGNORECASE):
            num_str = match.group(1).replace(' ', '').replace(',', '.')
            try:
                amount = float(num_str)
                results.append((typ, amount))
            except:
                continue
    return results

def extract_preorder_amounts(lines):
    """
    Для предзаказа: суммирует все найденные суммы по типам.
    Возвращает (cash, terminal, qr, installment).
    """
    cash = 0.0
    terminal = 0.0
    qr = 0.0
    installment = 0.0
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
            # 'prepayment' игнорируем, так как это не окончательная оплата
    return cash, terminal, qr, installment

def extract_sales_amounts(lines):
    """
    Для продаж: суммирует суммы по типам, игнорируя предоплату.
    """
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
# Обработчик для топика «Прибытие» (добавление товаров)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ARRIVAL)
async def handle_arrival(message: Message, bot):
    logger.info(f"📦 Сообщение в топике Прибытие от {message.from_user.id}")

    async def process_lines(lines, reply_to):
        lines = [line for line in lines if not re.match(r'^\s*-+\s*$', line)]
        if not lines:
            await reply_to("❌ Нет ни одной позиции после фильтрации.")
            return

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
            categories, idx = add_item_to_categories(line, categories)
            existing_texts.add(line)
            if serial:
                existing_serials.add(serial)
            added_lines.append(line)

        if added_lines:
            inventory.save_inventory(categories)

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
            await message.answer_document(
                doc,
                caption=f"✅ Добавлено: {len(added_lines)} | ⏭ Пропущено: {len(skipped_lines)}"
            )
        finally:
            os.unlink(tmp_path)

    if message.text:
        full_text = message.text.strip()
        if not full_text:
            await message.reply("❌ Пустой список.")
            return
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        await process_lines(lines, message.reply)
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
            await process_lines(lines, message.reply)
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        await message.reply("⚠️ Отправьте текст или файл .txt.")

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

    # Если есть брони, обрабатываем их по порядку
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
            # Определяем границы блока брони: от текущей строки до следующей брони или до конца
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

            # Удаляем старые записи с этим серийным номером
            categories, removed = inventory.remove_by_serial(categories, serial)
            today = datetime.now().strftime("%d.%m")
            new_item = f"{item_line} (Бронь от {today})"
            categories, idx = add_item_to_categories(new_item, categories)
            inventory.save_inventory(categories)

            stats.increment_booking(amount=total_amount)
            await message.react([ReactionTypeEmoji(emoji='👍')])
            await message.reply(f"✅ Добавлена бронь:\n{new_item}")

    else:
        # Нет брони – всё сообщение предзаказ
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
