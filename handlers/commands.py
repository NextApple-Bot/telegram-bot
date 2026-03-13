import csv
import json
import tempfile
import os
import asyncpg
from aiogram import F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

import config
from database import search_clients, get_client_purchases
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

        conn = await asyncpg.connect(config.DATABASE_URL)
        try:
            rows = await conn.fetch('SELECT * FROM clients ORDER BY id')
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
        finally:
            await conn.close()

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

        conn = await asyncpg.connect(config.DATABASE_URL)
        try:
            rows = await conn.fetch('SELECT * FROM purchases ORDER BY id')
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
        finally:
            await conn.close()

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

@router.message(Command("export_full_report"))
async def cmd_export_full_report(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID клиента', 'ФИО', 'Телефон', 'Telegram', 'Дата покупки', 'Товары', 'Сумма', 'Способ оплаты'])

        conn = await asyncpg.connect(config.DATABASE_URL)
        try:
            rows = await conn.fetch('''
                SELECT c.id, c.full_name, c.phone, c.telegram_username,
                       p.created_at, p.items_json, p.total_amount, p.payment_details
                FROM clients c
                LEFT JOIN purchases p ON c.id = p.client_id
                ORDER BY c.id, p.created_at
            ''')
            for row in rows:
                items = json.loads(row['items_json']) if row['items_json'] else []
                items_short = ', '.join([it['item_text'][:30] + '...' for it in items])
                writer.writerow([
                    row['id'],
                    row['full_name'],
                    row['phone'],
                    row['telegram_username'],
                    row['created_at'],
                    items_short,
                    row['total_amount'],
                    row['payment_details']
                ])
        finally:
            await conn.close()

        tmp_path = tmp.name

    try:
        await message.answer_document(
            FSInputFile(tmp_path, filename="full_report.csv"),
            caption="📁 Полный отчёт (клиенты и покупки)"
        )
    finally:
        os.unlink(tmp_path)

@router.message(Command("reset_clients"))
async def cmd_reset_clients(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        async with conn.transaction():
            await conn.execute("DELETE FROM purchases")
            await conn.execute("DELETE FROM clients")
        await message.answer("✅ Все данные клиентов и покупок удалены. Теперь учёт начнётся заново.")
    except Exception as e:
        logger.exception("Ошибка при сбросе клиентов")
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await conn.close()

# ---------- Команды для управления категориями ----------
@router.message(Command("show_categories"))
async def cmd_show_categories(message: Message):
    """Показать все категории с ID и количеством товаров."""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        rows = await conn.fetch('''
            SELECT c.id, c.name, COUNT(i.id) as item_count
            FROM categories c
            LEFT JOIN items i ON c.id = i.category_id
            GROUP BY c.id, c.name
            ORDER BY c.id
        ''')
        if not rows:
            await message.answer("📭 В базе нет категорий.")
            return

        text = "📋 **Список категорий:**\n\n"
        for r in rows:
            text += f"🆔 `{r['id']}` — **{r['name']}** (товаров: {r['item_count']})\n"
        await message.answer(text, parse_mode='Markdown')
    finally:
        await conn.close()

@router.message(Command("clean_empty"))
async def cmd_clean_empty(message: Message):
    """Удалить все пустые категории (с подтверждением)."""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        rows = await conn.fetch('''
            SELECT c.id, c.name
            FROM categories c
            LEFT JOIN items i ON c.id = i.category_id
            WHERE i.id IS NULL
        ''')
        if not rows:
            await message.answer("✅ Пустых категорий нет.")
            return

        categories_list = "\n".join([f"• {r['name']} (ID {r['id']})" for r in rows])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить все", callback_data="clean_empty:confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await message.answer(
            f"⚠️ Найдены пустые категории:\n{categories_list}\n\nУдалить их?",
            reply_markup=keyboard
        )
    finally:
        await conn.close()

@router.message(Command("reset_assortment"))
async def cmd_reset_assortment(message: Message):
    """Полностью очистить ассортимент (удалить все товары и категории)."""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    # Спрашиваем подтверждение
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, УДАЛИТЬ ВСЁ", callback_data="reset_assortment:confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
    ])
    await message.answer(
        "⚠️ **ВНИМАНИЕ!** Эта команда **полностью удалит** все товары и категории из ассортимента.\n"
        "Данные о клиентах, покупках, статистике и бронях сохранятся.\n\n"
        "Вы уверены?",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    
@router.message(Command("delete_category"))
async def cmd_delete_category(message: Message):
    """Удалить категорию по ID (только если она пуста)."""
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Используйте: /delete_category <ID>")
        return
    try:
        cat_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        cat = await conn.fetchrow('SELECT name FROM categories WHERE id = $1', cat_id)
        if not cat:
            await message.answer(f"❌ Категория с ID {cat_id} не найдена.")
            return

        count = await conn.fetchval('SELECT COUNT(*) FROM items WHERE category_id = $1', cat_id)
        if count > 0:
            await message.answer(f"❌ Категория «{cat['name']}» содержит {count} товаров. Удаление невозможно.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_cat:{cat_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await message.answer(
            f"⚠️ Точно удалить пустую категорию «{cat['name']}» (ID {cat_id})?",
            reply_markup=keyboard
        )
    finally:
        await conn.close()

@router.message(Command("migrate"))
async def cmd_migrate(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    conn = await asyncpg.connect(config.DATABASE_URL)
    try:
        # Добавляем поле is_booked
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS is_booked BOOLEAN DEFAULT FALSE')
        # Обновляем забронированные товары
        result = await conn.execute("UPDATE items SET is_booked = TRUE WHERE text ILIKE '%Бронь от%'")
        updated = result.split()[-1]
        # Создаём индекс
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_is_booked ON items(is_booked)')
        await message.answer(f"✅ Миграция выполнена!\nОбновлено записей: {updated}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        await conn.close()
