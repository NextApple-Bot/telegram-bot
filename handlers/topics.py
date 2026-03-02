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
import finances
from .base import (
    router, logger, AssortmentConfirmState, add_item_to_categories,
    sort_assortment_to_categories, build_output_text, get_main_menu_keyboard
)


# -------------------------------------------------------------------
# Вспомогательные функции для извлечения сумм и способов оплаты
# -------------------------------------------------------------------
def extract_amount(text):
    """
    Извлекает число (сумму) из строки. Ищет цифры, возможно с пробелами, 
    после которых могут быть слова 'руб', 'р.' или символ ₽.
    """
    match = re.search(r'(\d[\d\s]*\d|\d)\s*(?:руб|р\.|₽)?', text)
    if match:
        amount_str = match.group(1).replace(' ', '')
        try:
            return int(amount_str)
        except:
            return None
    return None

def extract_prepaid(line):
    """
    Извлекает предоплату из строки вида "П/О - 5000 (QR-код)".
    Возвращает кортеж (способ, сумма) или None.
    """
    # Ищем П/О или П\О, затем число
    match = re.search(r'П[/\\]О\s*[:\-]?\s*([\d\s]+)', line)
    if not match:
        return None
    amount_str = match.group(1).replace(' ', '')
    try:
        amount = int(amount_str)
    except:
        return None
    # Ищем способ оплаты в скобках
    method_match = re.search(r'\(([^)]+)\)', line)
    method = method_match.group(1).lower() if method_match else ""
    if "наличные" in method or "нал" in method:
        return ("cash", amount)
    elif "терминал" in method or "терм" in method:
        return ("terminal", amount)
    elif "qr" in method or "кьюар" in method or "код" in method:
        return ("qr", amount)
    else:
        # Если способ не распознан, игнорируем
        return None


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
        # Убираем строки, состоящие только из дефисов
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

    first_line = lines[0].strip().lower()

    # Обработка брони
    if re.match(r'^бронь\s*:?$', first_line):
        content_lines = lines[1:]
        if not content_lines:
            await message.reply("❌ Не найдено описание товара для брони.")
            return

        # Ищем строку с серийным номером
        item_line = None
        for line in content_lines:
            line = line.strip()
            if re.search(r'\([A-Z0-9-]{5,}\)', line, re.IGNORECASE):
                item_line = line
                break

        if not item_line:
            await message.reply("❌ Не удалось найти товар с серийным номером для брони.")
            return

        # Извлекаем серийный номер
        serial = inventory.extract_serial(item_line)
        if not serial:
            await message.reply("❌ Не удалось извлечь серийный номер.")
            return

        categories = inventory.load_inventory()

        # Проверяем, есть ли уже забронированный товар с таким серийным номером
        for cat in categories:
            for item in cat['items']:
                if inventory.extract_serial(item) == serial and "(Бронь от" in item:
                    await message.reply("⚠️ Этот товар уже забронирован.")
                    return

        # Удаляем все товары с таким серийным номером
        categories, removed = inventory.remove_by_serial(categories, serial)

        # Создаём новую строку с пометкой
        today = datetime.now().strftime("%d.%m")
        new_item = f"{item_line} (Бронь от {today})"

        # Добавляем новый товар
        categories, idx = add_item_to_categories(new_item, categories)
        inventory.save_inventory(categories)

        stats.increment_booking()

        await message.react([ReactionTypeEmoji(emoji='👍')])
        await message.reply(f"✅ Добавлена бронь:\n{new_item}")

        # Парсим возможные предоплаты (если они есть в брони – по желанию, пока не требуется)
        # Оставим на будущее

    else:
        # Это предзаказ – только счётчик и реакция 👌
        stats.increment_preorder()
        await message.react([ReactionTypeEmoji(emoji='👌')])

        # Парсим предоплаты из всех строк сообщения (кроме первой, но на всякий случай проходим по всем)
        for line in lines:
            prepaid = extract_prepaid(line)
            if prepaid:
                ptype, amount = prepaid
                finances.add_payment(ptype, amount)


# -------------------------------------------------------------------
# Обработчик для топика «Продажи» (удаление по серийным номерам + учёт оплат)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_SALES)
async def handle_sales_message(message: Message):
    logger.info(f"📩 Сообщение в топике Продажи: {message.text}")
    if not message.text:
        return

    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    if not lines:
        return

    # Сначала обрабатываем удаление по серийным номерам
    inv = inventory.load_inventory()
    removed_count = 0
    not_found_serials = []

    for line in lines:
        serials = inventory.extract_serials_from_text(line)
        if serials:
            for serial in serials:
                inv, removed = inventory.remove_by_serial(inv, serial)
                if removed:
                    removed_count += removed
                else:
                    not_found_serials.append(serial)
        # Если в строке нет серийных номеров, ничего не делаем (удаление по тексту отключено)

    if removed_count:
        inventory.save_inventory(inv)
        stats.increment_sales(removed_count)
        try:
            await message.react([ReactionTypeEmoji(emoji='🔥')])
        except Exception as e:
            logger.exception(f"Не удалось поставить реакцию: {e}")
        await message.reply(f"✅ Удалено позиций: {removed_count}")

    if not_found_serials:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(not_found_serials)
        await message.reply(text)
        logger.info(f"❌ Не найдены: {not_found_serials}")

    # Теперь парсим строки с оплатами (независимо от удаления)
    for line in lines:
        amount = extract_amount(line)
        if amount:
            lower_line = line.lower()
            if "наличные" in lower_line:
                finances.add_payment("cash", amount)
            elif "терминал" in lower_line:
                finances.add_payment("terminal", amount)
            elif "qr" in lower_line or "кьюар" in lower_line or "код" in lower_line:
                finances.add_payment("qr", amount)


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
