from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Chat, Message, User

from bot import config


@pytest.mark.asyncio
async def test_booking_flow_success(mock_bot):
    content = """БРОНЬ:
iPad Pro 11 (IPAD789) - 80000₽
П/О 20000 (нал)
Клиент: Петр Петров
Телефон: +79123456789
Площадка: Авито"""

    message = Message(
        message_id=456,
        chat=Chat(id=config.MAIN_GROUP_ID, type="supergroup"),
        text=content,
        message_thread_id=config.THREAD_PREORDER,
        from_user=User(id=12345, is_bot=False, first_name="Admin")
    )

    with patch('bot.handlers.topics.preorder.mark_message_processed', new=AsyncMock(return_value=True)), \
         patch('bot.handlers.topics.preorder.extract_prepayments', return_value={'cash': 20000.0, 'terminal': 0, 'qr': 0, 'transfer': 0, 'invoice': 0, 'installment': 0}), \
         patch('bot.handlers.topics.preorder.parse_client_data', return_value={
             'phones': ['+79123456789'], 'full_name': 'Петр Петров', 'main_phone': '+79123456789',
             'telegram_username': None, 'social_network': 'Авито', 'referral_source': None, 'birth_date': None
         }), \
         patch('bot.handlers.topics.preorder.ClientRepository.get_or_create_client', new=AsyncMock(return_value=1)), \
         patch('bot.handlers.topics.preorder.StatsRepository.add_preorder', new=AsyncMock()), \
         patch('bot.handlers.topics.preorder.PaymentService.add_payments_batch', new=AsyncMock()), \
         patch('bot.handlers.topics.preorder.safe_react', new=AsyncMock()), \
         patch('bot.handlers.topics.preorder.BookingService.process_booking', new=AsyncMock(return_value={
             "success": True, "results": [{"status": "booked"}]
         })), \
         patch('bot.handlers.topics.preorder.extract_payment_amounts', return_value={'cash': 0, 'terminal': 0, 'qr': 0, 'transfer': 0, 'invoice': 0, 'installment': 0}):

        from bot.handlers.topics.preorder import handle_preorder
        await handle_preorder(message)

    mock_bot.send_message.assert_called()
