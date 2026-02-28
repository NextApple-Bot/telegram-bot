import tempfile
import os
import aiofiles
from aiogram import F
from aiogram.types import Message, ReactionTypeEmoji, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from .base import (
    router, logger, UploadStates, process_new_objects,
    get_main_menu_keyboard, process_full_text, inventory
)

@router.message(UploadStates.waiting_for_inventory, F.text)
async def process_inventory_text_part(message: Message, bot, state):
    data = await state.get_data()
    parts = data.get("parts", [])
    parts.append(message.text.strip())
    await state.update_data(parts=parts)
    await message.react([ReactionTypeEmoji(emoji='👌')])
    await message.answer(f"✅ Часть {len(parts)} принята. Отправьте следующую или нажмите /done / кнопку «✅ Готово».")

@router.message(UploadStates.waiting_for_inventory, F.document)
async def process_inventory_document(message: Message, bot, state):
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
