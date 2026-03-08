from aiogram import F
from aiogram.types import Message

from .base import (
    router, UploadStates
)

# Временно отключаем старую логику загрузки через сообщения
@router.message(UploadStates.waiting_for_inventory, F.text)
async def process_inventory_text_part(message: Message, bot, state):
    await message.answer("⚠️ Функция загрузки через текстовые сообщения временно недоступна. Пожалуйста, используйте топик «Прибытие» для добавления товаров или топик «Ассортимент» для полной замены.")

@router.message(UploadStates.waiting_for_inventory, F.document)
async def process_inventory_document(message: Message, bot, state):
    await message.answer("⚠️ Функция загрузки через файлы временно недоступна. Пожалуйста, используйте топик «Прибытие» для добавления товаров или топик «Ассортимент» для полной замены.")

@router.message(UploadStates.waiting_for_inventory)
async def process_inventory_invalid(message: Message):
    await message.answer("⚠️ Пожалуйста, отправьте текстовое сообщение или текстовый файл. (Но сейчас этот режим временно недоступен)")
