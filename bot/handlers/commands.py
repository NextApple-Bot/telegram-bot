import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.utils.helpers import send_and_clean

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start(message: Message):
    logger.info(f"[CMD] /start от пользователя {message.from_user.id}")
    try:
        from .base import get_main_menu_keyboard
        keyboard = get_main_menu_keyboard()
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="Добро пожаловать! Используйте кнопки ниже для управления.",
            reply_markup=keyboard,
            message_thread_id=message.message_thread_id,
            delete_after=60,
        )
    except Exception:
        logger.exception("[CMD] Ошибка в /start")


@router.message(Command("inventory"))
async def cmd_inventory(message: Message):
    logger.info(f"[CMD] /inventory от пользователя {message.from_user.id}")
    try:
        from .base import show_inventory
        await show_inventory(message.bot, message.chat.id)
    except Exception:
        logger.exception("[CMD] Ошибка в /inventory")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state):
    logger.info(f"[CMD] /cancel от пользователя {message.from_user.id}")
    try:
        from .base import cancel_action, get_main_menu_keyboard
        await cancel_action(message.bot, message.chat.id, state)
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="Действие отменено. Главное меню:",
            reply_markup=get_main_menu_keyboard(),
            message_thread_id=message.message_thread_id,
            delete_after=60,
        )
    except Exception:
        logger.exception("[CMD] Ошибка в /cancel")


@router.message(Command("help"))
async def cmd_help(message: Message):
    logger.info(f"[CMD] /help от пользователя {message.from_user.id}")
    try:
        from .base import show_help
        await show_help(message.bot, message.chat.id)
    except Exception:
        logger.exception("[CMD] Ошибка в /help")
