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
    match = re.search(r'(?:Стоимость|Общая|Наличные|Наличными|Терминал|П/О|ПО|QR|QR-код|Рассрочка)\s*[-–—]?\s*([\d\s]+)(?:\.|р|руб)?', line, re.IGNORECASE)
    if match:
        num_str = match.group(1).replace(' ', '')
        try:
            return float(num_str)
        except:
            return 0.0
    return 0.0

def extract_preorder_amounts(lines):
    cash = 0.0
    terminal = 0.0
    qr = 0.0
    installment = 0.0
    for line in lines:
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

def extract_sales_amounts(lines):
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
# Остальные обработчики (Ассортимент, Прибытие, Продажи, экспорт) – без изменений
# (они уже были в предыдущих версиях, здесь не дублирую для краткости)
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# Обработчик для топика «Предзаказ» (брони/предзаказы) – ОБНОВЛЁН
# -------------------------------------------------------------------
@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_PREORDER)
async def handle_preorder(message: Message, bot):
    logger.info(f"📥 Сообщение в топике Предзаказ от {message.from_user.id}")

    if not message.text:
        return

    lines = message.text.strip().splitlines()
    if not lines:
        return

    # Ищем строку, начинающуюся с "Бронь:" (регистр не важен)
    booking_index = None
    for i, line in enumerate(lines):
        if re.match(r'^бронь\s*:?$', line.strip().lower()):
            booking_index = i
            break

    if booking_index is not None:
        # Обрабатываем бронь
        content_lines = lines[booking_index+1:]  # строки после "Бронь:"
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

        serial = inventory.extract_serial(item_line)
        if not serial:
            await message.reply("❌ Не удалось извлечь серийный номер.")
            return

        # Извлекаем все суммы из сообщения (для учёта в финансах)
        cash, terminal, qr, installment = extract_preorder_amounts(lines)
        total_amount = cash + terminal + qr + installment

        categories = inventory.load_inventory()

        # Проверка на уже забронированный товар
        for cat in categories:
            for item in cat['items']:
                if inventory.extract_serial(item) == serial and "(Бронь от" in item:
                    await message.reply("⚠️ Этот товар уже забронирован.")
                    return

        # Удаляем старые записи с этим серийным номером
        categories, removed = inventory.remove_by_serial(categories, serial)
        today = datetime.now().strftime("%d.%m")
        new_item = f"{item_line} (Бронь от {today})"
        categories, idx = add_item_to_categories(new_item, categories)
        inventory.save_inventory(categories)

        # Увеличиваем счётчик броней и сумму
        stats.increment_booking(amount=total_amount)
        await message.react([ReactionTypeEmoji(emoji='👍')])
        await message.reply(f"✅ Добавлена бронь:\n{new_item}")

    else:
        # Это предзаказ – извлекаем суммы и увеличиваем счётчик
        cash, terminal, qr, installment = extract_preorder_amounts(lines)
        stats.increment_preorder(cash=cash, terminal=terminal, qr=qr, installment=installment)
        await message.react([ReactionTypeEmoji(emoji='👌')])
