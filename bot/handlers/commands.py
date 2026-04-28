import csv
import json
import logging
import os
import secrets
import tempfile

import asyncpg
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.db import get_pool
from bot.repositories import ClientRepository, ItemRepository
from bot.utils.helpers import send_and_clean
from bot.utils.markdown import escape_markdown_v1

from .base import cancel_action, get_main_menu_keyboard, show_help, show_inventory

router = Router()
logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

@router.message(Command("start"))
async def cmd_start(message: Message):
    logger.info(f"🔥 Команда /start получена от {message.from_user.id}")
    try:
        keyboard = get_main_menu_keyboard()
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text="👋 Добро пожаловать! Используйте кнопки ниже для управления.",
            reply_markup=keyboard,
            message_thread_id=message.message_thread_id,
            delete_after=60
        )
    except Exception as e:
        logger.exception(f"❌ Ошибка при обработке /start: {e}")

@router.message(Command("inventory"))
async def cmd_inventory(message: Message, bot):
    await show_inventory(bot, message.chat.id)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot, state):
    await cancel_action(bot, message.chat.id, state)
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text="Главное меню:",
        reply_markup=get_main_menu_keyboard(),
        message_thread_id=message.message_thread_id,
        delete_after=60
    )

@router.message(Command("help"))
async def cmd_help(message: Message, bot):
    await show_help(bot, message.chat.id)

# ---------- Экспорт данных ----------
@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM clients ORDER BY id')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID', 'ФИО', 'Основной телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации'])
        for row in rows:
            created_at = row['created_at'].strftime("%d.%m.%y") if row['created_at'] else ''
            writer.writerow([
                row['id'],
                row['full_name'],
                row['phone'],
                row['phones'],
                row['telegram_username'],
                row['social_network'],
                row['referral_source'],
                created_at
            ])
        tmp_path = tmp.name

    try:
        await message.answer_document(FSInputFile(tmp_path, filename="clients.csv"), caption="📁 Экспорт клиентов")
    finally:
        os.unlink(tmp_path)

@router.message(Command("export_purchases"))
async def cmd_export_purchases(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM purchases ORDER BY id')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID покупки', 'ID клиента', 'Товары (JSON)', 'Сумма', 'Оплата (JSON)', 'Тип', 'Дата'])
        for row in rows:
            created_at = row['created_at'].strftime("%d.%m.%y") if row['created_at'] else ''
            writer.writerow([
                row['id'],
                row['client_id'],
                row['items_json'],
                row['total_amount'],
                row['payment_details'],
                row['purchase_type'],
                created_at
            ])
        tmp_path = tmp.name

    try:
        await message.answer_document(FSInputFile(tmp_path, filename="purchases.csv"), caption="📁 Экспорт покупок")
    finally:
        os.unlink(tmp_path)

@router.message(Command("client_info"))
async def cmd_client_info(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    args = message.text.replace('/client_info', '').strip()
    if not args:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Укажите телефон или имя клиента", message_thread_id=message.message_thread_id, delete_after=60)
        return

    clients = await ClientRepository.search_clients(args)
    if not clients:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="Клиент не найден", message_thread_id=message.message_thread_id, delete_after=60)
        return

    for client in clients:
        full_name = escape_markdown_v1(client['full_name'] or '—')
        phone = escape_markdown_v1(client['phone'] or '—')
        phones = escape_markdown_v1(client['phones'] or '—')
        telegram = escape_markdown_v1(f"@{client['telegram_username']}" if client['telegram_username'] else '—')
        social = escape_markdown_v1(client['social_network'] or '—')
        source = escape_markdown_v1(client['referral_source'] or '—')
        created_at = client['created_at'].strftime("%d.%m.%y") if client['created_at'] else '—'

        text = f"👤 *Клиент ID {client['id']}*\n"
        text += f"ФИО: {full_name}\n"
        text += f"Основной телефон: {phone}\n"
        text += f"Все телефоны: {phones}\n"
        text += f"Telegram: {telegram}\n"
        text += f"Соцсети: {social}\n"
        text += f"Источник: {source}\n"
        text += f"Дата регистрации: {created_at}\n\n"

        purchases = await ClientRepository.get_client_purchases(client['id'])
        if purchases:
            text += "*Покупки:*\n"
            for p in purchases:
                p_created = p['created_at'].strftime("%d.%m.%y") if p['created_at'] else '—'
                text += f"📅 {p_created}\n"
                items = json.loads(p['items_json']) if p['items_json'] else []
                for item in items:
                    item_text = escape_markdown_v1(item.get('item_text', '')[:50])
                    text += f"  • {item_text}"
                    if item.get('price'):
                        text += f" \\- {item['price']}₽"
                    text += "\n"
                text += f"  💰 Сумма: {p['total_amount']}₽\n"
                text += f"  💳 Оплата: {p['payment_details']}\n"
                text += f"  🏷️ Тип: {p['purchase_type']}\n\n"
        else:
            text += "Нет покупок\n"
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=text, parse_mode='Markdown', message_thread_id=message.message_thread_id, delete_after=60)

@router.message(Command("export_full_report"))
async def cmd_export_full_report(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT c.id, c.full_name, c.phone, c.telegram_username,
                   p.created_at, p.items_json, p.total_amount, p.payment_details
            FROM clients c
            LEFT JOIN purchases p ON c.id = p.client_id
            ORDER BY c.id, p.created_at
        ''')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID клиента', 'ФИО', 'Телефон', 'Telegram', 'Дата покупки', 'Товары', 'Сумма', 'Способ оплаты'])
        for row in rows:
            items = json.loads(row['items_json']) if row['items_json'] else []
            items_short = ', '.join([it.get('item_text', '')[:30] + '...' for it in items])
            p_created = row['created_at'].strftime("%d.%m.%y") if row['created_at'] else ''
            writer.writerow([
                row['id'],
                row['full_name'],
                row['phone'],
                row['telegram_username'],
                p_created,
                items_short,
                row['total_amount'],
                row['payment_details']
            ])
        tmp_path = tmp.name

    try:
        await message.answer_document(FSInputFile(tmp_path, filename="full_report.csv"), caption="📁 Полный отчёт (клиенты и покупки)")
    finally:
        os.unlink(tmp_path)

# ---------- Управление категориями ----------
@router.message(Command("show_categories"))
async def cmd_show_categories(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
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
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="📭 В базе нет категорий.", message_thread_id=message.message_thread_id, delete_after=60)
            return

        text = "📋 **Список категорий:**\n\n"
        for r in rows:
            text += f"🆔 `{r['id']}` — **{escape_markdown_v1(r['name'])}** (товаров: {r['item_count']})\n"
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=text, parse_mode='Markdown', message_thread_id=message.message_thread_id, delete_after=60)

@router.message(Command("clean_empty"))
async def cmd_clean_empty(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
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
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="✅ Пустых категорий нет.", message_thread_id=message.message_thread_id, delete_after=60)
            return

        categories_list = "\n".join([f"• {escape_markdown_v1(r['name'])} (ID {r['id']})" for r in rows])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить все", callback_data="clean_empty:confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=f"⚠️ Найдены пустые категории:\n{categories_list}\n\nУдалить их?",
            reply_markup=keyboard,
            message_thread_id=message.message_thread_id,
            delete_after=60
        )

@router.message(Command("delete_category"))
async def cmd_delete_category(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    args = message.text.split()
    if len(args) != 2:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Используйте: /delete_category <ID>", message_thread_id=message.message_thread_id, delete_after=60)
        return
    try:
        cat_id = int(args[1])
    except ValueError:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должен быть числом", message_thread_id=message.message_thread_id, delete_after=60)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        cat = await conn.fetchrow('SELECT name FROM categories WHERE id = $1', cat_id)
        if not cat:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=f"❌ Категория с ID {cat_id} не найдена.", message_thread_id=message.message_thread_id, delete_after=60)
            return

        count = await conn.fetchval('SELECT COUNT(*) FROM items WHERE category_id = $1', cat_id)
        if count > 0:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=f"❌ Категория «{escape_markdown_v1(cat['name'])}» содержит {count} товаров. Удаление невозможно.", message_thread_id=message.message_thread_id, delete_after=60)
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_cat:{cat_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=f"⚠️ Точно удалить пустую категорию «{escape_markdown_v1(cat['name'])}» (ID {cat_id})?",
            reply_markup=keyboard,
            message_thread_id=message.message_thread_id,
            delete_after=60
        )

@router.message(Command("merge_categories"))
async def cmd_merge_categories(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    args = message.text.split()
    if len(args) != 3:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Используйте: /merge_categories <from_id> <to_id>", message_thread_id=message.message_thread_id, delete_after=60)
        return
    try:
        from_id = int(args[1])
        to_id = int(args[2])
    except ValueError:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должны быть числами", message_thread_id=message.message_thread_id, delete_after=60)
        return

    if from_id == to_id:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должны быть разными", message_thread_id=message.message_thread_id, delete_after=60)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        from_cat = await conn.fetchrow('SELECT name FROM categories WHERE id = $1', from_id)
        to_cat = await conn.fetchrow('SELECT name FROM categories WHERE id = $1', to_id)
        if not from_cat or not to_cat:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Одна из категорий не найдена", message_thread_id=message.message_thread_id, delete_after=60)
            return

        count = await conn.fetchval('SELECT COUNT(*) FROM items WHERE category_id = $1', from_id)
        if count == 0:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=f"❌ В категории «{escape_markdown_v1(from_cat['name'])}» нет товаров. Удалите её через /delete_category.", message_thread_id=message.message_thread_id, delete_after=60)
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, перенести и удалить", callback_data=f"merge:{from_id}:{to_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=f"⚠️ Перенести {count} товаров из «{escape_markdown_v1(from_cat['name'])}» (ID {from_id}) в «{escape_markdown_v1(to_cat['name'])}» (ID {to_id})?\nПосле этого категория {from_id} будет удалена.",
            reply_markup=keyboard,
            message_thread_id=message.message_thread_id,
            delete_after=60
        )

@router.message(Command("reset_assortment"))
async def cmd_reset_assortment(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ ДА, УДАЛИТЬ ВСЁ", callback_data="reset_assortment:confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
    ])
    await send_and_clean(
        bot=message.bot,
        chat_id=message.chat.id,
        text="⚠️ **ВНИМАНИЕ!** Эта команда **полностью удалит** все товары и категории из ассортимента.\nДанные о клиентах, покупках, статистике и бронях сохранятся.\n\nВы уверены?",
        reply_markup=keyboard,
        parse_mode='Markdown',
        message_thread_id=message.message_thread_id,
        delete_after=60
    )

# ---------- Удаление по ID ----------
@router.message(Command("delete_client"))
async def cmd_delete_client(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    args = message.text.split()
    if len(args) != 2:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Используйте: /delete_client <ID>", message_thread_id=message.message_thread_id, delete_after=60)
        return
    try:
        client_id = int(args[1])
    except ValueError:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должен быть числом", message_thread_id=message.message_thread_id, delete_after=60)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        client = await conn.fetchrow('SELECT full_name FROM clients WHERE id = $1', client_id)
        if not client:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=f"❌ Клиент с ID {client_id} не найден.", message_thread_id=message.message_thread_id, delete_after=60)
            return

        purchases = await conn.fetchval('SELECT COUNT(*) FROM purchases WHERE client_id = $1', client_id)
        warning = f"\n⚠️ У клиента есть {purchases} покупок — они будут удалены вместе с клиентом." if purchases else ""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_client:{client_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=f"⚠️ Удалить клиента «{escape_markdown_v1(client['full_name'] or 'Без имени')}» (ID {client_id})?{warning}",
            reply_markup=keyboard,
            message_thread_id=message.message_thread_id,
            delete_after=60
        )

@router.message(Command("delete_purchase"))
async def cmd_delete_purchase(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    args = message.text.split()
    if len(args) != 2:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ Используйте: /delete_purchase <ID>", message_thread_id=message.message_thread_id, delete_after=60)
        return
    try:
        purchase_id = int(args[1])
    except ValueError:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ ID должен быть числом", message_thread_id=message.message_thread_id, delete_after=60)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        purchase = await conn.fetchrow('SELECT id, total_amount FROM purchases WHERE id = $1', purchase_id)
        if not purchase:
            await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=f"❌ Покупка с ID {purchase_id} не найдена.", message_thread_id=message.message_thread_id, delete_after=60)
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_purchase:{purchase_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=f"⚠️ Удалить покупку ID {purchase_id} на сумму {purchase['total_amount']} ₽?",
            reply_markup=keyboard,
            message_thread_id=message.message_thread_id,
            delete_after=60
        )

# ---------- Команда /undo ----------
@router.message(Command("undo"))
async def cmd_undo(message: Message):
    if not is_admin(message.from_user.id):
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    deleted = await ItemRepository.get_last_deleted_item()
    if not deleted:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="📭 Нет удалённых товаров для восстановления.", message_thread_id=message.message_thread_id, delete_after=60)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        cat = await conn.fetchval('SELECT id FROM categories WHERE id = $1', deleted['category_id'])
        if not cat:
            cat_id = await ItemRepository.get_or_create_category("Общее:")
        else:
            cat_id = deleted['category_id']

    await ItemRepository.add_item(
        text=deleted['text'],
        serial=deleted['serial'],
        category_id=cat_id
    )
    await ItemRepository.restore_deleted_item(deleted['id'])

    await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=f"✅ Товар восстановлен:\n{escape_markdown_v1(deleted['text'])}", message_thread_id=message.message_thread_id, delete_after=60)

# ---------- Команда /chatid ----------
@router.message(Command("chatid"))
async def cmd_chatid(message: Message):
    chat_id = message.chat.id
    thread_id = message.message_thread_id
    response = f"Chat ID: `{chat_id}`\n"
    if thread_id:
        response += f"Thread ID: `{thread_id}`"
    else:
        response += "Thread ID: отсутствует (сообщение не в топике)"
    await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=response, parse_mode="Markdown", message_thread_id=message.message_thread_id, delete_after=60)

# ---------- Команда для исправления таблицы sales ----------
@router.message(Command("fix_sales_unique"))
async def cmd_fix_sales_unique(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        result1 = await conn.execute('DELETE FROM sales WHERE message_id IS NULL')
        deleted_null = result1.split()[1] if result1.startswith('DELETE') else 0

        result2 = await conn.execute('''
            DELETE FROM sales a USING sales b
            WHERE a.id > b.id AND a.message_id = b.message_id
        ''')
        deleted_dups = result2.split()[1] if result2.startswith('DELETE') else 0

        constraint_added = False
        try:
            await conn.execute('ALTER TABLE sales ADD CONSTRAINT sales_message_id_key UNIQUE (message_id)')
            constraint_added = True
        except asyncpg.exceptions.DuplicateTableError:
            pass
        except Exception as e:
            logger.exception(f"Ошибка при добавлении ограничения: {e}")

    msg = f"✅ Исправление таблицы sales:\n• Удалено записей с NULL message_id: {deleted_null}\n• Удалено дубликатов: {deleted_dups}\n• Уникальное ограничение: {'добавлено' if constraint_added else 'уже существовало'}"
    await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=msg, message_thread_id=message.message_thread_id, delete_after=60)

# ---------- Команда для переустановки вебхука ----------
@router.message(Command("set_webhook"))
async def cmd_set_webhook(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="⛔ Доступ запрещён", message_thread_id=message.message_thread_id, delete_after=60)
        return

    if not config.RENDER_URL:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text="❌ RENDER_URL не задан в переменных окружения.", message_thread_id=message.message_thread_id, delete_after=60)
        return

    webhook_url = f"{config.RENDER_URL}/webhook"
    webhook_secret = os.getenv("WEBHOOK_SECRET")
    if not webhook_secret:
        webhook_secret = secrets.token_urlsafe(32)
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=f"⚠️ WEBHOOK_SECRET не задан, использован временный:\n`{webhook_secret}`\nРекомендуется добавить его в .env", parse_mode='Markdown', message_thread_id=message.message_thread_id, delete_after=60)

    try:
        from aiogram import Bot
        temp_bot = Bot(token=config.TOKEN)
        await temp_bot.delete_webhook(drop_pending_updates=True)
        await temp_bot.set_webhook(
            url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=["message", "callback_query"]
        )
        await temp_bot.session.close()
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=f"✅ Вебхук успешно установлен на:\n{webhook_url}\nСекретный токен: `{webhook_secret}`", parse_mode='Markdown', message_thread_id=message.message_thread_id, delete_after=60)
    except Exception as e:
        await send_and_clean(bot=message.bot, chat_id=message.chat.id, text=f"❌ Ошибка при установке вебхука:\n{str(e)}", message_thread_id=message.message_thread_id, delete_after=60)
