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

# ====== Вспомогательные функции для извлечения сумм ======
def extract_amount_from_line(line):
    """Извлекает число из строки, если есть ключевое слово. Возвращает float или 0."""
    match = re.search(r'(?:Стоимость|Общая|Наличные|Наличными|Терминал|П/О|ПО|QR|QR-код|Рассрочка)\s*[-–—]?\s*([\d\s]+)(?:\.|р|руб)?', line, re.IGNORECASE)
    if match:
        num_str = match.group(1).replace(' ', '')
        try:
            return float(num_str)
        except:
            return 0.0
    return 0.0

def extract_preorder_amounts(lines):
    """
    Для предзаказа: извлекает суммы по типам оплаты.
    Возвращает (cash, terminal, qr, installment) – суммы, найденные в сообщении.
    """
    cash = 0.0
    terminal = 0.0
    qr = 0.0
    installment = 0.0
    for line in lines:
        # Пропускаем строки с "П/О", если они не должны учитываться? В предзаказах П/О – это предоплата, обычно наличными или через QR.
        # Будем считать, что "П/О" – это тоже предоплата, её тип можно определить по наличию слов "Наличные", "QR" и т.д. Но проще пока не разделять.
        # Для простоты: ищем ключевые слова в строке и добавляем сумму к соответствующему типу.
        amount = extract_amount_from_line(line)
        if amount == 0:
            continue
        if re.search(r'Наличные|Наличными', line, re.IGNORECASE):
            cash += amount
        elif re.search(r'Терминал', line, re.IGNORECASE):
            terminal += amount
        elif re.search(r'QR|QR-код', line, re.IGNORECASE):
            qr += amount
        elif re.search(r'Рассрочка', line, re.IGNORECASE):
            installment += amount
        else:
            # Если нет ключевого слова, возможно, это общая стоимость – можно добавить в общую сумму, но не в конкретный тип.
            # Оставим пока без типа.
            pass
    return cash, terminal, qr, installment

def extract_sales_amounts(lines):
    """
    Для продаж: извлекает суммы по типам оплаты, игнорируя строки с П/О.
    """
    cash = 0.0
    terminal = 0.0
    qr = 0.0
    installment = 0.0
    for line in lines:
        if re.search(r'П/О|ПО', line, re.IGNORECASE):
            continue
        amount = extract_amount_from_line(line)
        if amount == 0:
            continue
        if re.search(r'Наличные|Наличными', line, re.IGNORECASE):
            cash += amount
        elif re.search(r'Терминал', line, re.IGNORECASE):
            terminal += amount
        elif re.search(r'QR|QR-код', line, re.IGNORECASE):
            qr += amount
        elif re.search(r'Рассрочка', line, re.IGNORECASE):
            installment += amount
    return cash, terminal, qr, installment

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

    if re.match(r'^бронь\s*:?$', first_line):
        # ... (код для брони без изменений, только увеличивает счётчик броней)
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

        categories, removed = inventory.remove_by_serial(categories, serial)
        today = datetime.now().strftime("%d.%m")
        new_item = f"{item_line} (Бронь от {today})"
        categories, idx = add_item_to_categories(new_item, categories)
        inventory.save_inventory(categories)

        stats.increment_booking()
        await message.react([ReactionTypeEmoji(emoji='👍')])
        await message.reply(f"✅ Добавлена бронь:\n{new_item}")

    else:
        # Это предзаказ – извлекаем суммы по типам
        cash, terminal, qr, installment = extract_preorder_amounts(lines)
        stats.increment_preorder(cash=cash, terminal=terminal, qr=qr, installment=installment)
        await message.react([ReactionTypeEmoji(emoji='👌')])
        # Можно добавить ответ с суммой, если нужно
        # await message.reply(f"✅ Предзаказ зарегистрирован. Суммы: нал={cash}, терм={terminal}, qr={qr}, расср={installment}")

# -------------------------------------------------------------------
# Обработчик для топика «Продажи» (удаление по серийным номерам)
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
        lines = message.text.splitlines()
        cash, terminal, qr, installment = extract_sales_amounts(lines)
        stats.increment_sales(count=len(found_serials), cash=cash, terminal=terminal, qr=qr, installment=installment)
        try:
            await message.react([ReactionTypeEmoji(emoji='🔥')])
        except Exception as e:
            logger.exception(f"Не удалось поставить реакцию: {e}")
    if not_found_serials:
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(not_found_serials)
        await message.reply(text)
        logger.info(f"❌ Не найдены: {not_found_serials}")
