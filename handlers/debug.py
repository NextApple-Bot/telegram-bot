from aiogram import Router, F
from aiogram.types import Message
import logging

logger = logging.getLogger(__name__)

# Создаём отдельный роутер для временного логирования
debug_router = Router()

# Логируем все сообщения в группах и супергруппах
@debug_router.message(F.chat.type.in_({'group', 'supergroup'}))
async def log_group_message(message: Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    text_sample = message.text[:50] if message.text else "[не текст]"
    logger.info(f"🔍 Сообщение в группе {chat_id}, thread_id={thread_id}, текст: {text_sample}")
