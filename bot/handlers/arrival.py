import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()
logger = logging.getLogger(__name__)


@router.message()
async def handle_arrival_file(message: Message):
    """Обработка файлов с новым ассортиментом в топике 'прибытие'."""
    if not message.document:
        return

    # Проверяем, что это топик "прибытие" (ID можно настроить в config)
    # Пока просто логируем
    logger.info(f"Получен файл в топике: {message.message_thread_id}, файл: {message.document.file_name}")

    # TODO: Здесь должна быть логика парсинга Excel и обновления ассортимента
    await message.answer(
        "📥 Файл получен!\n\n"
        "⚠️ Функция автоматического обновления ассортимента из файла временно отключена.\n"
        "Пожалуйста, используйте кнопки в меню или напишите @NextAppleSupport для ручного обновления.",
        reply_to_message_id=message.message_id
    )
