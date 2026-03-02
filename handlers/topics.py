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
import undo
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
    match = re.search(r'П[/\\]О\s*[:\-]?\s*([\d\s]+)', line)
    if not match:
        return None
    amount_str = match.group(1).replace(' ', '')
    try:
        amount = int(amount_str)
    except:
        return None
    method_match = re.search(r'\(([^)]+)\)', line)
    method = method_match.group(1).lower() if method_match else ""
    if "наличные" in method or "нал" in method:
        return ("cash", amount)
    elif "терминал" in method or "терм" in method:
        return ("terminal", amount)
    elif "qr" in method or "кьюар" in method or "код" in method:
        return ("qr", amount)
    else:
        return None


# -------------------------------------------------------------------
# Обработчик для топика «Ассортимент» (без изменений)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ASSORTMENT)
async def handle_assortment_upload(message: Message, bot, state):
    logger.info(f"📥 Загрузка ассортимента в топик Ассортимент от {message.from_user.id}")
    # ... (код без изменений, как в предыдущей версии)
    # (для краткости я не буду повторять, он остаётся таким же)


@router.callback_query(AssortmentConfirmState.waiting_for_confirm, F.data.startswith("assort_confirm:"))
async def process_assortment_confirm(callback: CallbackQuery, state):
    # ... (без изменений)
    pass


# -------------------------------------------------------------------
# Обработчик для топика «Прибытие» (без изменений)
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_ARRIVAL)
async def handle_arrival(message: Message, bot):
    # ... (без изменений)
    pass


# -------------------------------------------------------------------
# Обработчик для топика «Предзаказ» (брони/предзаказы) + отмена
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_PREORDER)
async def handle_preorder(message: Message, bot):
    logger.info(f"📥 Сообщение в топике Предзаказ от {message.from_user.id}")

    if not message.text:
        return

    text = message.text.strip()
    if not text:
        return

    # Проверка на команду отмены
    if text.lower() == "отмена":
        action = undo.get_action()
        if not action:
            await message.reply("❌ Нет действия для отмены.")
            return
        if action["type"] not in ("preorder", "booking"):
            await message.reply("❌ Последнее действие не было предзаказом или бронью.")
            return

        if action["type"] == "preorder":
            # Откатываем предзаказ
            stats.add_preorder(-1)
            await message.reply("✅ Последний предзаказ отменён.")
        elif action["type"] == "booking":
            # Откатываем бронь: удаляем добавленный товар и уменьшаем счётчик
            data = action["data"]
            # Удаляем товар с серийным номером из инвентаря
            categories = inventory.load_inventory()
            serial_to_remove = data["serial"]
            # Удаляем все товары с этим серийным номером (обычно один)
            categories, _ = inventory.remove_by_serial(categories, serial_to_remove)
            inventory.save_inventory(categories)
            stats.add_booking(-1)
            await message.reply("✅ Последняя бронь отменена.")
        undo.clear_action()
        return

    # Основная обработка (как и раньше)
    lines = text.splitlines()
    if not lines:
        return

    first_line = lines[0].strip().lower()

    # Обработка брони
    if re.match(r'^бронь\s*:?$', first_line):
        content_lines = lines[1:]
        if not content_lines:
            await message.reply("❌ Не найдено описание товара для брони.")
            return

        item_line = None
        for line in content_lines:
            line = line.strip()
            if re.search(r'\([A-Z0-9-]{5,}\)', line, re.IGNORECASE):
                item_line = line
                break

        if not item_line:
            await message.reply("❌ Не удалось найти товар с серийным номером для брони.")
            return

        serial = inventory.extract_serial(item_line)
        if not serial:
            await message.reply("❌ Не удалось извлечь серийный номер.")
            return

        categories = inventory.load_inventory()

        # Проверка на уже забронированный товар
        for cat in categories:
            for item in cat['items']:
                if inventory.extract_serial(item) == serial and "(Бронь от" in item:
                    await message.reply("⚠️ Этот товар уже забронирован.")
                    return

        # Удаляем старые записи с этим серийным номером
        categories, removed = inventory.remove_by_serial(categories, serial)

        # Создаём новую строку с пометкой
        today = datetime.now().strftime("%d.%m")
        new_item = f"{item_line} (Бронь от {today})"

        categories, idx = add_item_to_categories(new_item, categories)
        inventory.save_inventory(categories)

        stats.add_booking(1)

        await message.react([ReactionTypeEmoji(emoji='👍')])
        await message.reply(f"✅ Добавлена бронь:\n{new_item}")

        # Сохраняем действие для возможной отмены
        undo.save_action("booking", {"serial": serial, "item": new_item})

    else:
        # Это предзаказ – только счётчик и реакция
        stats.add_preorder(1)
        await message.react([ReactionTypeEmoji(emoji='👌')])

        # Парсим предоплаты
        payments = []
        for line in lines:
            prepaid = extract_prepaid(line)
            if prepaid:
                ptype, amount = prepaid
                finances.add_payment(ptype, amount)
                payments.append((ptype, amount))

        # Сохраняем действие для отмены
        undo.save_action("preorder", {"payments": payments})


# -------------------------------------------------------------------
# Обработчик для топика «Продажи» (удаление + оплаты) + отмена
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_SALES)
async def handle_sales_message(message: Message):
    logger.info(f"📩 Сообщение в топике Продажи: {message.text}")
    if not message.text:
        return

    text = message.text.strip()
    if not text:
        return

    # Проверка на команду отмены
    if text.lower() == "отмена":
        action = undo.get_action()
        if not action:
            await message.reply("❌ Нет действия для отмены.")
            return
        if action["type"] != "sales":
            await message.reply("❌ Последнее действие не было продажей.")
            return

        data = action["data"]
        # Откатываем удалённые товары
        categories = inventory.load_inventory()
        for removed in data["removed_items"]:
            cat_name = removed["category"]
            item_text = removed["item"]
            # Ищем категорию и добавляем товар обратно
            found = False
            for cat in categories:
                if cat["header"] == cat_name:
                    cat["items"].append(item_text)
                    found = True
                    break
            if not found:
                # Если категория исчезла (маловероятно), создаём новую
                categories.append({"header": cat_name, "items": [item_text]})
        inventory.save_inventory(categories)

        # Откатываем статистику продаж
        stats.add_sales(-data["sales_count"])

        # Откатываем финансы
        for payment in data["payments"]:
            ptype, amount = payment
            finances.add_payment(ptype, -amount)

        undo.clear_action()
        await message.reply("✅ Последняя продажа отменена.")
        return

    # Основная обработка
    lines = text.splitlines()
    if not lines:
        return

    inv = inventory.load_inventory()
    removed_count = 0
    not_found_serials = []
    removed_items_info = []  # для сохранения в undo

    # Обработка удаления по серийным номерам
    for line in lines:
        serials = inventory.extract_serials_from_text(line)
        if serials:
            for serial in serials:
                # Ищем товары с этим серийным номером, чтобы запомнить их для отмены
                for cat in inv:
                    for item in cat['items']:
                        if inventory.extract_serial(item) == serial:
                            removed_items_info.append({"category": cat['header'], "item": item})
                inv, removed = inventory.remove_by_serial(inv, serial)
                if removed:
                    removed_count += removed
                else:
                    not_found_serials.append(serial)

    if removed_count:
        inventory.save_inventory(inv)
        stats.add_sales(removed_count)
        try:
            await message.react([ReactionTypeEmoji(emoji='🔥')])
        except Exception as e:
            logger.exception(f"Не удалось поставить реакцию: {e}")
        await message.reply(f"✅ Удалено позиций: {removed_count}")

    if not_found_serials:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(not_found_serials)
        await message.reply(text)
        logger.info(f"❌ Не найдены: {not_found_serials}")

    # Парсим оплаты
    payments = []
    for line in lines:
        # Пропускаем строки с предоплатой
        if re.search(r'П[/\\]О', line, re.IGNORECASE):
            continue
        amount = extract_amount(line)
        if amount:
            lower_line = line.lower()
            if "наличные" in lower_line:
                ptype = "cash"
            elif "терминал" in lower_line:
                ptype = "terminal"
            elif "qr" in lower_line or "кьюар" in lower_line or "код" in lower_line:
                ptype = "qr"
            else:
                continue
            finances.add_payment(ptype, amount)
            payments.append((ptype, amount))

    # Сохраняем действие для отмены, если были изменения
    if removed_count > 0 or payments:
        undo.save_action("sales", {
            "removed_items": removed_items_info,
            "sales_count": removed_count,
            "payments": payments
        })
    else:
        # Если ничего не изменилось, удаляем предыдущее действие? Лучше не трогать.
        pass
