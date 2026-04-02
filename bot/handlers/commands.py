import csv
import json
import tempfile
import os
import logging
from aiogram import Router
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import asyncpg

from bot import config
from bot.db import get_pool
from bot.repositories import ClientRepository, ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.markdown import escape_markdown_v1
from .base import show_inventory, cancel_action, get_main_menu_keyboard, show_help

router = Router()
logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

@router.message(Command("start"))
async def cmd_start(message: Message):
    logger.info(f"🔥 Команда /start получена от {message.from_user.id}")
    try:
        keyboard = get_main_menu_keyboard()
        await message.answer(
            "👋 Добро пожаловать! Используйте кнопки ниже для управления.",
            reply_markup=keyboard
        )
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

# ---------- Экспорт данных ----------
@router.message(Command("export_clients"))
async def cmd_export_clients(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM clients ORDER BY id')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID', 'ФИО', 'Основной телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации'])
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
        await message.answer_document(FSInputFile(tmp_path, filename="clients.csv"), caption="📁 Экспорт клиентов")
    finally:
        os.unlink(tmp_path)

@router.message(Command("export_purchases"))
async def cmd_export_purchases(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM purchases ORDER BY id')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID покупки', 'ID клиента', 'Товары (JSON)', 'Сумма', 'Оплата (JSON)', 'Тип', 'Дата'])
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
        await message.answer_document(FSInputFile(tmp_path, filename="purchases.csv"), caption="📁 Экспорт покупок")
    finally:
        os.unlink(tmp_path)

@router.message(Command("client_info"))
async def cmd_client_info(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    args = message.text.replace('/client_info', '').strip()
    if not args:
        await message.answer("Укажите телефон или имя клиента")
        return

    clients = await ClientRepository.search_clients(args)
    if not clients:
        await message.answer("Клиент не найден")
        return

    for client in clients:
        full_name = escape_markdown_v1(client['full_name'] or '—')
        phone = escape_markdown_v1(client['phone'] or '—')
        phones = escape_markdown_v1(client['phones'] or '—')
        telegram = escape_markdown_v1(f"@{client['telegram_username']}" if client['telegram_username'] else '—')
        social = escape_markdown_v1(client['social_network'] or '—')
        source = escape_markdown_v1(client['referral_source'] or '—')
        
        text = f"👤 *Клиент ID {client['id']}*\n"
        text += f"ФИО: {full_name}\n"
        text += f"Основной телефон: {phone}\n"
        text += f"Все телефоны: {phones}\n"
        text += f"Telegram: {telegram}\n"
        text += f"Соцсети: {social}\n"
        text += f"Источник: {source}\n"
        text += f"Дата регистрации: {client['created_at']}\n\n"

        purchases = await ClientRepository.get_client_purchases(client['id'])
        if purchases:
            text += "*Покупки:*\n"
            for p in purchases:
                text += f"📅 {p['created_at']}\n"
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
        await message.answer(text, parse_mode='Markdown')

@router.message(Command("export_full_report"))
async def cmd_export_full_report(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
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
        tmp_path = tmp.name

    try:
        await message.answer_document(FSInputFile(tmp_path, filename="full_report.csv"), caption="📁 Полный отчёт (клиенты и покупки)")
    finally:
        os.unlink(tmp_path)

# ---------- Управление категориями ----------
@router.message(Command("show_categories"))
async def cmd_show_categories(message: Message):
    if not is_admin(message.from_user.id):
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
            text += f"🆔 `{r['id']}` — **{escape_markdown_v1(r['name'])}** (товаров: {r['item_count']})\n"
        await message.answer(text, parse_mode='Markdown')

@router.message(Command("clean_empty"))
async def cmd_clean_empty(message: Message):
    if not is_admin(message.from_user.id):
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

        categories_list = "\n".join([f"• {escape_markdown_v1(r['name'])} (ID {r['id']})" for r in rows])
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
    if not is_admin(message.from_user.id):
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
            await message.answer(f"❌ Категория «{escape_markdown_v1(cat['name'])}» содержит {count} товаров. Удаление невозможно.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_cat:{cat_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await message.answer(
            f"⚠️ Точно удалить пустую категорию «{escape_markdown_v1(cat['name'])}» (ID {cat_id})?",
            reply_markup=keyboard
        )

@router.message(Command("merge_categories"))
async def cmd_merge_categories(message: Message):
    if not is_admin(message.from_user.id):
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
            await message.answer(f"❌ В категории «{escape_markdown_v1(from_cat['name'])}» нет товаров. Удалите её через /delete_category.")
            return

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, перенести и удалить", callback_data=f"merge:{from_id}:{to_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await message.answer(
            f"⚠️ Перенести {count} товаров из «{escape_markdown_v1(from_cat['name'])}» (ID {from_id}) в «{escape_markdown_v1(to_cat['name'])}» (ID {to_id})?\n"
            f"После этого категория {from_id} будет удалена.",
            reply_markup=keyboard
        )

@router.message(Command("reset_assortment"))
async def cmd_reset_assortment(message: Message):
    if not is_admin(message.from_user.id):
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

# ---------- Удаление по ID ----------
@router.message(Command("delete_client"))
async def cmd_delete_client(message: Message):
    if not is_admin(message.from_user.id):
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
        warning = f"\n⚠️ У клиента есть {purchases} покупок — они будут удалены вместе с клиентом." if purchases else ""

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_client:{client_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:cancel")]
        ])
        await message.answer(
            f"⚠️ Удалить клиента «{escape_markdown_v1(client['full_name'] or 'Без имени')}» (ID {client_id})?{warning}",
            reply_markup=keyboard
        )

@router.message(Command("delete_purchase"))
async def cmd_delete_purchase(message: Message):
    if not is_admin(message.from_user.id):
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

# ---------- Команда /undo ----------
@router.message(Command("undo"))
async def cmd_undo(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    deleted = await ItemRepository.get_last_deleted_item()
    if not deleted:
        await message.answer("📭 Нет удалённых товаров для восстановления.")
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

    await message.answer(f"✅ Товар восстановлен:\n{escape_markdown_v1(deleted['text'])}")

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
    await message.reply(response, parse_mode="Markdown")

# ---------- Команда для исправления таблицы sales ----------
@router.message(Command("fix_sales_unique"))
async def cmd_fix_sales_unique(message: Message):
    """Добавляет уникальное ограничение на message_id в таблице sales (только для админов)."""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён")
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # 1. Удаляем записи с NULL message_id
            result1 = await conn.execute('DELETE FROM sales WHERE message_id IS NULL')
            deleted_null = result1.split()[1] if result1.startswith('DELETE') else 0

            # 2. Удаляем дубликаты (оставляем одну запись на message_id)
            result2 = await conn.execute('''
                DELETE FROM sales a USING sales b 
                WHERE a.id > b.id AND a.message_id = b.message_id
            ''')
            deleted_dups = result2.split()[1] if result2.startswith('DELETE') else 0

            # 3. Добавляем уникальное ограничение, если его нет
            constraint_added = False
            try:
                await conn.execute('ALTER TABLE sales ADD CONSTRAINT sales_message_id_key UNIQUE (message_id)')
                constraint_added = True
            except asyncpg.exceptions.DuplicateTableError:
                # Ограничение уже существует
                pass
            except Exception as e:
                logger.exception(f"Ошибка при добавлении ограничения: {e}")

    msg = f"✅ Исправление таблицы sales:\n"
    msg += f"• Удалено записей с NULL message_id: {deleted_null}\n"
    msg += f"• Удалено дубликатов: {deleted_dups}\n"
    msg += f"• Уникальное ограничение: {'добавлено' if constraint_added else 'уже существовало'}"
    await message.answer(msg)


# ---------- Команда для переустановки вебхука ----------
@router.message(Command("set_webhook"))
async def cmd_set_webhook(message: Message):
    """Переустанавливает вебхук (только для админов)."""
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён")
        return

    if not config.RENDER_URL:
        await message.answer("❌ RENDER_URL не задан в переменных окружения.")
        return

    webhook_url = f"{config.RENDER_URL}/webhook"
    webhook_secret = os.getenv("WEBHOOK_SECRET")
    if not webhook_secret:
        import secrets
        webhook_secret = secrets.token_urlsafe(32)
        await message.answer(f"⚠️ WEBHOOK_SECRET не задан, использован временный:\n`{webhook_secret}`\nРекомендуется добавить его в .env", parse_mode='Markdown')

    try:
        from aiogram import Bot
        from bot import config as bot_config
        temp_bot = Bot(token=bot_config.TOKEN)
        
        await temp_bot.delete_webhook(drop_pending_updates=True)
        await temp_bot.set_webhook(
            url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=["message", "callback_query"]
        )
        await temp_bot.session.close()
        
        await message.answer(f"✅ Вебхук успешно установлен на:\n{webhook_url}\nСекретный токен: `{webhook_secret}`", parse_mode='Markdown')
    except Exception as e:
        await message.answer(f"❌ Ошибка при установке вебхука:\n{str(e)}")
