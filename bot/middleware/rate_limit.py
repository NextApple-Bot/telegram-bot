import logging
import time
from collections import defaultdict
from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.config import config

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """
    Простой in-memory rate limiter для Telegram-бота.
    Защищает от спама и DDoS-атак.
    """

    def __init__(self, calls: int = 20, period: int = 60):
        self.calls = calls          # сколько запросов разрешено
        self.period = period        # за сколько секунд
        self.storage: defaultdict = defaultdict(list)  # user_id -> [timestamps]

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        user_id = user.id
        now = time.time()

        # Очищаем старые записи
        self.storage[user_id] = [t for t in self.storage[user_id] if now - t < self.period]

        # Проверяем лимит
        if len(self.storage[user_id]) >= self.calls:
            logger.warning(f"Rate limit exceeded for user {user_id}")
            # Можно отправить сообщение пользователю
            try:
                bot = data.get("bot")
                if bot:
                    await bot.send_message(
                        chat_id=user_id,
                        text="⏳ Слишком много запросов. Подождите немного.",
                        message_thread_id=getattr(event, "message_thread_id", None)
                    )
            except Exception:
                pass  # не ломаем обработку

            return  # блокируем дальнейшую обработку

        # Добавляем текущий timestamp
        self.storage[user_id].append(now)

        return await handler(event, data)


# ==================== Глобальный экземпляр ====================
rate_limit = RateLimitMiddleware(calls=25, period=60)
