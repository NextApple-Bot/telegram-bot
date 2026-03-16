import csv
import json
import tempfile
import os
from aiogram import F, Router
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

import config
from database import search_clients, get_client_purchases, get_pool
from .base import (
    router as base_router, logger, show_inventory, cancel_action,
    get_main_menu_keyboard, show_help
)

router = Router()

# ... (команды start, inventory, cancel, help, export_clients, export_purchases, client_info, export_full_report остаются без изменений, они используют get_pool)

@router.message(Command("show_categories"))
async def cmd_show_categories(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
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

@router.message(Command("clean_empty"))
async def cmd_clean_empty(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
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

@router.message(Command("delete_category"))
async def cmd_delete_category(message: Message):
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

    pool = await get_pool()
    async with pool.acquire() as conn:
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

@router.message(Command("merge_categories"))
async def cmd_merge_categories(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    args = message.text.split()
    if len(args) != 3:
        await message.answer("❌ Используйте: /merge_categories <from_id> <to_id>")
        return
    try:
        from_id = int(args[1])
        to_id = int(args[2])
    except ValueError:
        await message.answer("❌ ID должны быть числами")
        return

    if from_id == to_id:
        await message.answer("❌ ID должны быть разными")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        from_cat = await conn.fetchrow('SELECT name FROM categories WHERE id = $1', from_id)
        to_cat = await conn.fetchrow('SELECT name FROM categories WHERE id = $1', to_id)
        if not from_cat or not to_cat:
            await message.answer("❌ Одна из категорий не найдена")
            return

        count = await conn.fetchval('SELECT COUNT(*) FROM items WHERE category_id = $1', from_id)
        if count == 0:
            await message.answer(f"❌ В категории «{from_cat['name']}» нет товаров. Удалите её через /delete_category.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, перенести и удалить", callback_data=f"merge:{from_id}:{to_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await message.answer(
            f"⚠️ Перенести {count} товаров из «{from_cat['name']}» (ID {from_id}) в «{to_cat['name']}» (ID {to_id})?\n"
            f"После этого категория {from_id} будет удалена.",
            reply_markup=keyboard
        )

@router.message(Command("reset_assortment"))
async def cmd_reset_assortment(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

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

@router.message(Command("delete_client"))
async def cmd_delete_client(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Используйте: /delete_client <ID>")
        return
    try:
        client_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        client = await conn.fetchrow('SELECT full_name FROM clients WHERE id = $1', client_id)
        if not client:
            await message.answer(f"❌ Клиент с ID {client_id} не найден.")
            return

        purchases = await conn.fetchval('SELECT COUNT(*) FROM purchases WHERE client_id = $1', client_id)
        if purchases:
            warning = f"\n⚠️ У клиента есть {purchases} покупок — они будут удалены вместе с клиентом."
        else:
            warning = ""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_client:{client_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await message.answer(
            f"⚠️ Удалить клиента «{client['full_name'] or 'Без имени'}» (ID {client_id})?{warning}",
            reply_markup=keyboard
        )

@router.message(Command("delete_purchase"))
async def cmd_delete_purchase(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ Используйте: /delete_purchase <ID>")
        return
    try:
        purchase_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        purchase = await conn.fetchrow('SELECT id, total_amount FROM purchases WHERE id = $1', purchase_id)
        if not purchase:
            await message.answer(f"❌ Покупка с ID {purchase_id} не найдена.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_purchase:{purchase_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await message.answer(
            f"⚠️ Удалить покупку ID {purchase_id} на сумму {purchase['total_amount']} ₽?",
            reply_markup=keyboard
        )

@router.message(Command("migrate"))
async def cmd_migrate(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Доступ запрещён")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS is_booked BOOLEAN DEFAULT FALSE')
            result = await conn.execute("UPDATE items SET is_booked = TRUE WHERE text ILIKE '%Бронь от%'")
            updated = result.split()[-1]
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_is_booked ON items(is_booked)')
            await message.answer(f"✅ Миграция выполнена!\nОбновлено записей: {updated}")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("chatid"))
async def cmd_chatid(message: Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    response = f"Chat ID: `{chat_id}`\n"
    if thread_id:
        response += f"Thread ID: `{thread_id}`"
    else:
        response += "Thread ID: отсутствует (сообщение не в топике)"
    await message.reply(response, parse_mode="Markdown")
