import re
import logging
from datetime import datetime
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

import config
import inventory
import stats
from utils import extract_payment_amounts
from database import get_item_by_text, get_item_by_serial, add_item

logger = logging.getLogger(__name__)
router = Router()

@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_PREORDER,
    (F.text | F.caption)
)
async def handle_preorder(message: Message):
    content = message.text or message.caption
    if not content:
        return

    lines = content.strip().splitlines()
    logger.info(f"Получено сообщение, строк: {len(lines)}")

    # Определяем, есть ли в сообщении блоки "Бронь:"
    booking_indices = [i for i, line in enumerate(lines) if re.match(r'^бронь\s*:?$', line.strip().lower())]
    logger.info(f"Найдены индексы брони: {booking_indices}")

    if booking_indices:
        # Есть брони – обрабатываем предварительную часть (до первой брони) как предзаказ
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            payments = extract_payment_amounts('\n'.join(preorder_lines), ignore_prepay=False)
            logger.info(f"Предзаказ (до брони): платежи {payments}")
            await stats.increment_preorder(**payments)
            await message.react([ReactionTypeEmoji(emoji='👌')])

        # Обрабатываем каждый блок брони
        for idx in booking_indices:
            start = idx + 1
            end = booking_indices[booking_indices.index(idx) + 1] if booking_indices.index(idx) + 1 < len(booking_indices) else len(lines)
            booking_lines = lines[start:end]
            logger.info(f"Блок брони #{idx}: строки = {booking_lines}")

            # Извлекаем все строки с товарами (с серийниками)
            item_lines = []
            for line in booking_lines:
                line = line.strip()
                if not line:
                    continue
                serial = inventory.extract_serial(line)
                logger.info(f"Строка: '{line}' -> извлечён серийник: {serial}")
                if serial:
                    item_lines.append(line)

            logger.info(f"Распознанные товары в блоке: {item_lines}")

            if not item_lines:
                await message.reply("❌ Не удалось найти товары с серийными номерами для брони.")
                continue

            # Извлекаем оплаты из блока брони (они включают П/О)
            payments = extract_payment_amounts('\n'.join(booking_lines), ignore_prepay=False)
            logger.info(f"Платежи в блоке брони: {payments}")
            total_paid = sum(payments.values())
            amount_per_item = total_paid / len(item_lines) if total_paid else 0

            for item_line in item_lines:
                logger.info(f"Обработка товара: {item_line}")
                item_info = await get_item_by_text(item_line)
                if not item_info:
                    serial = inventory.extract_serial(item_line)
                    if serial:
                        item_info = await get_item_by_serial(serial)

                if not item_info:
                    await message.reply(f"❌ Товар не найден: {item_line}")
                    continue

                item_text = item_info['text']
                category_name = item_info['category_name']
                serial = inventory.extract_serial(item_text)

                # Удаляем товар из основного ассортимента
                removed = await inventory.remove_by_serial(serial)
                if not removed:
                    await message.reply(f"❌ Не удалось удалить товар {item_text}.")
                    continue

                # Создаём запись о брони (товар помечается как забронированный)
                today = datetime.now().strftime("%d.%m")
                new_item_text = f"{item_text} (Бронь от {today})"
                await add_item(new_item_text, serial, category_name=category_name)

                # Сохраняем бронь в статистику
                await stats.increment_booking(serial, amount_per_item)

                await message.react([ReactionTypeEmoji(emoji='👍')])
                await message.reply(f"✅ Добавлена бронь:\n{new_item_text}")
    else:
        # Обычный предзаказ без броней
        payments = extract_payment_amounts(content, ignore_prepay=False)
        logger.info(f"Предзаказ без броней: платежи {payments}")
        await stats.increment_preorder(**payments)
        await message.react([ReactionTypeEmoji(emoji='👌')])                    serial = inventory.extract_serial(item_line)
                    if serial:
                        item_info = await get_item_by_serial(serial)

                if not item_info:
                    await message.reply(f"❌ Товар не найден: {item_line}")
                    continue

                item_text = item_info['text']
                category_name = item_info['category_name']
                serial = inventory.extract_serial(item_text)

                # Удаляем товар из основного ассортимента
                removed = await inventory.remove_by_serial(serial)
                if not removed:
                    await message.reply(f"❌ Не удалось удалить товар {item_text}.")
                    continue

                # Создаём запись о брони (товар помечается как забронированный)
                today = datetime.now().strftime("%d.%m")
                new_item_text = f"{item_text} (Бронь от {today})"
                await add_item(new_item_text, serial, category_name=category_name)

                # Сохраняем бронь в статистику
                await stats.increment_booking(serial, amount_per_item)

                await message.react([ReactionTypeEmoji(emoji='👍')])
                await message.reply(f"✅ Добавлена бронь:\n{new_item_text}")
    else:
        # Обычный предзаказ без броней
        payments = extract_payment_amounts(content, ignore_prepay=False)
        await stats.increment_preorder(**payments)
        await message.react([ReactionTypeEmoji(emoji='👌')])
