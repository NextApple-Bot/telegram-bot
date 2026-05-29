import asyncio
import logging
from aiogram import Bot
from aiogram.types import Message
from bot import config

logger = logging.getLogger(__name__)


async def send_and_clean(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_to_message_id: int = None,
    message_thread_id: int = None,
    delete_after: int = 60,
    parse_mode: str = None,
    disable_notification: bool = False,
    reply_markup=None,
    **kwargs
) -> Message:
    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
        parse_mode=parse_mode,
        disable_notification=disable_notification,
        reply_markup=reply_markup,
        **kwargs
    )

    if message_thread_id != config.THREAD_ASSORTMENT:
        async def delete_later():
            await asyncio.sleep(delete_after)
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение {msg.message_id}: {e}")

        asyncio.create_task(delete_later())

    return msg
