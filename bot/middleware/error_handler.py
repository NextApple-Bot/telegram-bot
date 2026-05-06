import asyncio
import logging
import traceback
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseMiddleware):
    """Middleware, который перехватывает исключения в хендлерах и логирует их."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            logger.error(f"❌ Необработанное исключение при обработке {type(event).__name__}: {e}\n{traceback.format_exc()}")
            user: User | None = data.get("event_from_user")
            asyncio.create_task(self._notify_admins(e, user, event))
            return None

    async def _notify_admins(self, exception: Exception, user: User | None, event: TelegramObject):
        try:
            from telegram_alerter import send_alert
            user_info = f" от {user.full_name} (@{user.username})" if user else ""
            msg = f"🚨 Ошибка в боте{user_info}\n{type(exception).__name__}: {exception}"
            await send_alert(msg, is_critical=True)
        except Exception as notify_err:
            logger.error(f"Не удалось отправить алерт: {notify_err}")
