import asyncio
import logging
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    """Перехватывает все ошибки в хендлерах и уведомляет админов."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            user: User | None = data.get("event_from_user")
            event_type = type(event).__name__

            logger.error(
                f"❌ Необработанное исключение в {event_type}\n"
                f"Пользователь: {user.id if user else 'Unknown'} {user.full_name if user else ''}\n"
                f"{traceback.format_exc()}"
            )

            # Асинхронное уведомление (не блокируем)
            asyncio.create_task(self._notify_admins(e, user, event))
            return None   # продолжаем работу бота

    async def _notify_admins(self, exception: Exception, user: User | None, event: TelegramObject):
        try:
            from telegram_alerter import send_alert   # ваш существующий алертер

            user_info = f" от {user.full_name} (@{user.username})" if user else ""
            msg = (
                f"🚨 Критическая ошибка в боте{user_info}\n"
                f"Тип: {type(exception).__name__}\n"
                f"Сообщение: {exception}"
            )
            await send_alert(msg, is_critical=True)
        except Exception as notify_err:
            logger.error(f"Не удалось отправить алерт админам: {notify_err}")
