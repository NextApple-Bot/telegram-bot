import csv
import tempfile
import os
import json
import aiosqlite
from aiogram import F
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

import config
from database import DB_PATH, search_clients, get_client_purchases
from .base import (
    router, logger, show_inventory, cancel_action, get_main_menu_keyboard, show_help
)

@router.message(Command("start"))
async def cmd_start(message: Message, bot):
    logger.info(f"🔥 Команда /start получена от {message.from_user.id}")
    try:
        keyboard = get_main_menu_keyboard()
        await message.answer(
            "👋 Добро пожаловать! Используйте кнопки ниже для управления.",
            reply_markup=keyboard
        )
        logger.info(f"✅ Ответ на /start отправлен пользователю {message.from_user.id}")
    except Exception as e:
        logger.exception(f"❌ Ошибка при обработке /start: {e}")

@router.message(Command("inventory"))
async def cmd_inventory(message: Message, bot):
    await show_inventory(bot, message.chat.id)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot, state):
    await cancel_action(bot, message.chat.id, state)
    await message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())

@router.message(Command("help"))
async def cmd_help(message: Message, bot):
    await show_help(bot, message.chat.id)

@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID', 'ФИО', 'Основной телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации'])

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM clients ORDER BY id')
            rows = await cursor.fetchall()
            for row in rows:
                writer.writerow([
                    row['id'],
                    row['full_name'],
                    row['phone'],
                    row['phones'],
                    row['telegram_username'],
                    row['social_network'],
                    row['referral_source'],
                    row['created_at']
                ])

        tmp_path = tmp.name

    try:
        await message.answer_document(
            FSInputFile(tmp_path, filename="clients.csv"),
            caption="📁 Экспорт клиентов"
        )
    finally:
        os.unlink(tmp_path)

@router.message(Command("export_purchases"))
async def cmd_export_purchases(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID покупки', 'ID клиента', 'Товары (JSON)', 'Сумма', 'Оплата (JSON)', 'Тип', 'Дата'])

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('SELECT * FROM purchases ORDER BY id')
            rows = await cursor.fetchall()
            for row in rows:
                writer.writerow([
                    row['id'],
                    row['client_id'],
                    row['items_json'],
                    row['total_amount'],
                    row['payment_details'],
                    row['purchase_type'],
                    row['created_at']
                ])

        tmp_path = tmp.name

    try:
        await message.answer_document(
            FSInputFile(tmp_path, filename="purchases.csv"),
            caption="📁 Экспорт покупок"
        )
    finally:
        os.unlink(tmp_path)

@router.message(Command("client_info"))
async def cmd_client_info(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    args = message.text.replace('/client_info', '').strip()
    if not args:
        await message.answer("Укажите телефон или имя клиента")
        return

    clients = await search_clients(args)
    if not clients:
        await message.answer("Клиент не найден")
        return

    for client in clients:
        text = f"👤 *Клиент ID {client['id']}*\n"
        text += f"ФИО: {client['full_name'] or '—'}\n"
        text += f"Основной телефон: {client['phone'] or '—'}\n"
        text += f"Все телефоны: {client['phones'] or '—'}\n"
        text += f"Telegram: @{client['telegram_username'] or '—'}\n"
        text += f"Соцсети: {client['social_network'] or '—'}\n"
        text += f"Источник: {client['referral_source'] or '—'}\n"
        text += f"Дата регистрации: {client['created_at']}\n\n"

        purchases = await get_client_purchases(client['id'])
        if purchases:
            text += "*Покупки:*\n"
            for p in purchases:
                text += f"📅 {p['created_at']}\n"
                items = json.loads(p['items_json']) if p['items_json'] else []
                for item in items:
                    text += f"  • {item['item_text'][:50]}"
                    if item.get('price'):
                        text += f" - {item['price']}₽"
                    text += "\n"
                text += f"  💰 Сумма: {p['total_amount']}₽\n"
                text += f"  💳 Оплата: {p['payment_details']}\n"
                text += f"  🏷️ Тип: {p['purchase_type']}\n\n"
        else:
            text += "Нет покупок\n"
        await message.answer(text, parse_mode='Markdown')
