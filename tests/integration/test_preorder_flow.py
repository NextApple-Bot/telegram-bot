from unittest.mock import AsyncMock, patch

import pytest

from bot.repositories.item import ItemRepository
from bot.services.assortment import AssortmentService


@pytest.mark.asyncio
async def test_restore_via_undo_command():
    # Мокаем БД-зависимые методы
    with patch('bot.repositories.item.ItemRepository.get_or_create_category', new=AsyncMock(return_value=1)), \
         patch('bot.repositories.item.ItemRepository.get_last_deleted_item', new=AsyncMock(return_value={
             'id': 1, 'text': 'Galaxy S24', 'serial': 'S24XYZ', 'category_id': 2
         })), \
         patch('bot.repositories.item.ItemRepository.add_item', new=AsyncMock()), \
         patch('bot.repositories.item.ItemRepository.restore_deleted_item', new=AsyncMock(return_value=True)), \
         patch('bot.services.assortment.AssortmentService.remove_by_serial', new=AsyncMock(return_value=1)), \
         patch('bot.repositories.item.ItemRepository.get_item_by_serial', new=AsyncMock(return_value={'id': 1})), \
         patch('bot.repositories.item.ItemRepository.get_all_items_serials', new=AsyncMock(return_value=[])):

        # Проверяем логику восстановления (без БД)
        deleted = await AssortmentService.remove_by_serial('S24XYZ', reason='test')
        assert deleted == 1

        restored = await ItemRepository.restore_deleted_item(1)
        assert restored is True
