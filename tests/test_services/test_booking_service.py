# Файл: tests/test_services/test_booking_service.py
import pytest
from unittest.mock import AsyncMock, patch
from bot.services.booking import BookingService

@pytest.mark.asyncio
async def test_process_booking_success():
    booking_lines = ["iPhone 15 Pro (ABC123)", "Наличные 500"]
    with patch('bot.services.booking.extract_serials', return_value=["ABC123"]), \
         patch('bot.services.booking.ItemRepository.get_item_by_text', return_value={'id': 1, 'text': 'iPhone 15 Pro'}), \
         patch('bot.services.booking.ItemRepository.mark_item_booked', new=AsyncMock()), \
         patch('bot.services.booking.StatsRepository.add_booking', new=AsyncMock()), \
         patch('bot.services.booking.extract_payment_amounts', return_value={'cash': 500, 'terminal': 0, 'qr': 0, 'transfer': 0, 'invoice': 0, 'installment': 0}):
        result = await BookingService.process_booking(booking_lines)
        assert result['success'] is True
        assert len(result['results']) == 1
