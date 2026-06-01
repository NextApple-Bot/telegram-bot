import logging
from aiogram import F, Router
from aiogram.types import Message

from bot import config

logger = logging.getLogger(__name__)
router = Router()

@router.message(F.chat.id == config.MAIN_GROUP_ID)
async def debug_any_message(message: Message):
    thread_id = getattr(message, 'message_thread_id', None)
    logger.warning(f"📩 Получено сообщение | thread_id={thread_id} | текст: {message.text[:80] if message.text else 'нет текста'}")
    
    if thread_id == config.THREAD_ARRIVAL:
        await message.reply(f"✅ Это топик Прибытие (thread_id={thread_id})")
    else:
        await message.reply(f"❌ Это НЕ топик Прибытие\nТвой thread_id = `{thread_id}`\nОжидается: `{config.THREAD_ARRIVAL}`")

print("Debug router loaded")
