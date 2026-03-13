import re
from datetime import datetime
from aiogram import F, Router
from aiogram.types import Message, ReactionTypeEmoji

import config
import inventory
import stats
from utils import extract_preorder_amounts
from database import get_item_by_text, get_item_by_serial, add_item

router = Router()

@router.message(F.chat.id == config.MAIN_GROUP_ID, F.message_thread_id == config.THREAD_PREORDER)
async def handle_preorder(message: Message):
    """Обрабатывает сообщение в топике Предзаказ (предзаказы и брони)."""
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

            item_lines = []
            for line in booking_lines:
                line = line.strip()
                if not line:
                    continue
                if inventory.extract_serial(line):
                    item_lines.append(line)

            if not item_lines:
                await message.reply("❌ Не удалось найти товары с серийными номерами для брони.")
                continue

            block_cash, block_terminal, block_qr, block_installment = extract_preorder_amounts(booking_lines)
            block_total = block_cash + block_terminal + block_qr + block_installment
            amount_per_item = block_total / len(item_lines) if block_total else 0

            for item_line in item_lines:
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

                removed = await inventory.remove_by_serial(serial)
                if not removed:
                    await message.reply(f"❌ Не удалось удалить товар {item_text}.")
                    continue

                today = datetime.now().strftime("%d.%m")
                new_item_text = f"{item_text} (Бронь от {today})"
                await add_item(new_item_text, serial, category_name=category_name)

                await stats.increment_booking(serial, amount_per_item)

                await message.react([ReactionTypeEmoji(emoji='👍')])
                await message.reply(f"✅ Добавлена бронь:\n{new_item_text}")

    else:
        cash, terminal, qr, installment = extract_preorder_amounts(lines)
        await stats.increment_preorder(cash, terminal, qr, installment)
        await message.react([ReactionTypeEmoji(emoji='👌')])
