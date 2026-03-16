from aiogram import Router, F
from aiogram.types import Message
import logging

logger = logging.getLogger(__name__)

debug_router = Router()

@debug_router.message(F.chat.type.in_({'group', 'supergroup'}))
async def log_group_message(message: Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    text_snippet = message.text[:100] if message.text else "[не текст]"
    logger.info(f"📢 Групповое сообщение | chat_id: {chat_id} | thread_id: {thread_id} | текст: {text_snippet}")
