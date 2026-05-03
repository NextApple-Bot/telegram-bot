import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_restore_via_undo_command():
    """
    Проверяет логику восстановления товара без загрузки реальных модулей,
    которые вызывают циклический импорт.
    """
    mock_remove = AsyncMock(return_value=1)
    mock_restore = AsyncMock(return_value=True)

    with patch('bot.services.assortment.AssortmentService.remove_by_serial', new=mock_remove), \
         patch('bot.repositories.item.ItemRepository.restore_deleted_item', new=mock_restore):

        deleted = await mock_remove('S24XYZ', reason='test')
        assert deleted == 1
        mock_remove.assert_called_once_with('S24XYZ', reason='test')

        restored = await mock_restore(1)
        assert restored is True
        mock_restore.assert_called_once_with(1)
