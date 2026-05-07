import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import config
from bot.handlers.states import AssortmentConfirmState
from bot.repositories.item import ItemRepository

logger = logging.getLogger(__name__)
router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024

@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ASSORTMENT,
    (F.text | F.caption | F.document)
)
async def handle_assortment_upload(message: Message, bot, state: FSMContext):
    # ... (чтение файла/текста, парсинг) без изменений
    # Замена ассортимента:
    @router.callback_query(AssortmentConfirmState.waiting_for_confirm, F.data.startswith("assort_confirm:"))
    async def process_assortment_confirm(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        categories = data.get("temp_categories")
        action = callback.data.split(":")[1]
        if action == "yes" and categories:
            try:
                await ItemRepository.bulk_replace_assortment(categories)
                await callback.message.edit_text("✅ Ассортимент загружен.")
            except Exception as e:
                logger.exception("Ошибка замены ассортимента")
                await callback.message.edit_text(f"❌ Ошибка: {e}")
        else:
            await callback.message.edit_text("❌ Загрузка отменена.")
        await state.clear()
