import logging
from aiogram import F, Router
from aiogram.types import Message

from bot import config

logger = logging.getLogger(__name__)
router = Router()

@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_ARRIVAL
)
async def debug_arrival(message: Message):
    logger.warning(f"🔥 ARRIVAL TRIGGERED | thread_id={message.message_thread_id}")
    await message.reply(
        f"✅ Хендлер сработал!\n\n"
        f"Твой thread_id: `{message.message_thread_id}`\n"
        f"Ожидаемый (из config): `{config.THREAD_ARRIVAL}`"
    )

print("✅ Debug arrival router loaded")
