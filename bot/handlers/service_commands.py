import csv
import json
import logging
import os
import tempfile

from bot.db import get_pool
from bot.repositories import ClientRepository, ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.markdown import escape_markdown_v1

logger = logging.getLogger(__name__)


# ─── Экспорт данных ─────────────────────────────────────────────
async def export_clients_csv() -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM clients ORDER BY id')
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID', 'ФИО', 'Основной телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации'])
        for row in rows:
            writer.writerow([
                row['id'], row['full_name'], row['phone'], row['phones'],
                row['telegram_username'], row['social_network'], row['referral_source'],
                row['created_at'].strftime("%d.%m.%y") if row['created_at'] else ''
            ])
        return tmp.name

async def export_purchases_csv() -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM purchases ORDER BY id')
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
        writer = csv.writer(tmp)
        writer.writerow(['ID покупки', 'ID клиента', 'Товары (JSON)', 'Сумма', 'Оплата (JSON)', 'Тип', 'Дата'])
        for row in rows:
            created_at = row['created_at'].strftime("%d.%m.%y") if row['created_at'] else ''
            writer.writerow([row['id'], row['client_id'], row['items_json'], row['total_amount'],
                             row['payment_details'], row['purchase_type'], created_at])
        return tmp.name

async def get_client_info_text(query: str) -> str | None:
    clients = await ClientRepository.search_clients(query)
    if not clients:
        return None
    parts = []
    for client in clients:
        full_name = escape_markdown_v1(client['full_name'] or '—')
        phone = escape_markdown_v1(client['phone'] or '—')
        phones = escape_markdown_v1(client['phones'] or '—')
        telegram = escape_markdown_v1(f"@{client['telegram_username']}" if client['telegram_username'] else '—')
        social = escape_markdown_v1(client['social_network'] or '—')
        source = escape_markdown_v1(client['referral_source'] or '—')
        created_at = client['created_at'].strftime("%d.%m.%y") if client['created_at'] else '—'
        text = f"👤 *Клиент ID {client['id']}*\n"
        text += f"ФИО: {full_name}\nТелефон: {phone}\nДоп. телефоны: {phones}\nTelegram: {telegram}\nСоцсети: {social}\nИсточник: {source}\nДата регистрации: {created_at}\n\n"
        purchases = await ClientRepository.get_client_purchases(client['id'])
        if purchases:
            text += "*Покупки:*\n"
            for p in purchases:
                p_created = p['created_at'].strftime("%d.%m.%y") if p['created_at'] else '—'
                text += f"📅 Дата покупки: {p_created}\n"
                items = json.loads(p['items_json']) if p['items_json'] else []
                for item in items:
                    item_text = escape_markdown_v1(item.get('item_text', '')[:50])
                    text += f"  • {item_text}"
                    if item.get('price'):
                        text += f" \\- {item['price']}₽"
                    text += "\n"
                text += f"  💰 Сумма: {p['total_amount']}₽\n  💳 Оплата: {p['payment_details']}\n  🏷️ Тип: {p['purchase_type']}\n\n"
        else:
            text += "Нет покупок\n"
        parts.append(text)
    return "\n\n".join(parts)

async def export_full_report_csv() -> str:
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
            writer.writerow([row['id'], row['full_name'], row['phone'], row['telegram_username'],
                             p_created, items_short, row['total_amount'], row['payment_details']])
        return tmp.name

# ─── Управление категориями ─────────────────────────────────────
async def list_categories_text() -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT c.id, c.name, COUNT(i.id) as item_count
            FROM categories c
            LEFT JOIN items i ON c.id = i.category_id
            GROUP BY c.id, c.name
            ORDER BY c.id
        ''')
    text = "📋 **Список категорий:**\n\n"
    for r in rows:
        text += f"🆔 `{r['id']}` — **{escape_markdown_v1(r['name'])}** (товаров: {r['item_count']})\n"
    return text

async def find_empty_categories() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return [dict(r) for r in await conn.fetch('''
            SELECT c.id, c.name FROM categories c
            LEFT JOIN items i ON c.id = i.category_id
            WHERE i.id IS NULL
        ''')]

async def delete_category_if_empty(cat_id: int) -> tuple[bool, str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cat = await conn.fetchrow('SELECT name FROM categories WHERE id = $1', cat_id)
        if not cat:
            return False, f"❌ Категория с ID {cat_id} не найдена."
        count = await conn.fetchval('SELECT COUNT(*) FROM items WHERE category_id = $1', cat_id)
        if count > 0:
            return False, f"❌ Категория «{escape_markdown_v1(cat['name'])}» содержит {count} товаров. Удаление невозможно."
        return True, f"«{escape_markdown_v1(cat['name'])}» (ID {cat_id})"

async def merge_categories(from_id: int, to_id: int) -> tuple[bool, str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        from_cat = await conn.fetchrow('SELECT name FROM categories WHERE id = $1', from_id)
        to_cat = await conn.fetchrow('SELECT name FROM categories WHERE id = $1', to_id)
        if not from_cat or not to_cat:
            return False, "❌ Одна из категорий не найдена"
        count = await conn.fetchval('SELECT COUNT(*) FROM items WHERE category_id = $1', from_id)
        if count == 0:
            return False, f"❌ В категории «{escape_markdown_v1(from_cat['name'])}» нет товаров. Удалите её через /delete_category."
        msg = f"⚠️ Перенести {count} товаров из «{escape_markdown_v1(from_cat['name'])}» (ID {from_id}) в «{escape_markdown_v1(to_cat['name'])}» (ID {to_id})?\nПосле этого категория {from_id} будет удалена."
        return True, msg

async def reset_assortment() -> str:
    """Полностью очищает ассортимент: удаляет все товары и категории, кроме системных."""
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM items WHERE category_id NOT IN (SELECT id FROM categories WHERE name = '__SYSTEM__')")
        await conn.execute("DELETE FROM categories WHERE name != '__SYSTEM__'")
    await AssortmentService.invalidate_cache()
    return "✅ Ассортимент полностью очищен"

# ─── Удаление по ID ─────────────────────────────────────────────
async def delete_client_by_id(client_id: int) -> tuple[bool, str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        client = await conn.fetchrow('SELECT full_name FROM clients WHERE id = $1', client_id)
        if not client:
            return False, f"❌ Клиент с ID {client_id} не найден."
        purchases = await conn.fetchval('SELECT COUNT(*) FROM purchases WHERE client_id = $1', client_id)
        warning = f"⚠️ Удалить клиента «{escape_markdown_v1(client['full_name'] or 'Без имени')}» (ID {client_id})?"
        if purchases:
            warning += f"\n⚠️ У клиента есть {purchases} покупок — они будут удалены вместе с клиентом."
        return True, warning

async def delete_purchase_by_id(purchase_id: int) -> tuple[bool, str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        purchase = await conn.fetchrow('SELECT id, total_amount FROM purchases WHERE id = $1', purchase_id)
        if not purchase:
            return False, f"❌ Покупка с ID {purchase_id} не найдена."
        return True, f"⚠️ Удалить покупку ID {purchase_id} на сумму {purchase['total_amount']} ₽?"

async def undo_last_deletion() -> str:
    deleted = await ItemRepository.get_last_deleted_item()
    if not deleted:
        return "📭 Нет удалённых товаров для восстановления."
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
    return f"✅ Товар восстановлен:\n{escape_markdown_v1(deleted['text'])}"

async def fix_sales_unique() -> str:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        result1 = await conn.execute('DELETE FROM sales WHERE message_id IS NULL')
        deleted_null = result1.split()[1] if result1.startswith('DELETE') else 0
        result2 = await conn.execute('''
            DELETE FROM sales a USING sales b
            WHERE a.id > b.id AND a.message_id = b.message_id
        ''')
        deleted_dups = result2.split()[1] if result2.startswith('DELETE') else 0
        try:
            await conn.execute('ALTER TABLE sales ADD CONSTRAINT sales_message_id_key UNIQUE (message_id)')
            constraint_added = True
        except Exception:
            constraint_added = False
    return f"✅ Исправление таблицы sales:\n• Удалено записей с NULL message_id: {deleted_null}\n• Удалено дубликатов: {deleted_dups}\n• Уникальное ограничение: {'добавлено' if constraint_added else 'уже существовало'}"

async def set_webhook_manually() -> str:
    import secrets

    from aiogram import Bot

    from bot import config
    if not config.RENDER_URL:
        return "❌ RENDER_URL не задан в переменных окружения."
    webhook_url = f"{config.RENDER_URL}/webhook"
    webhook_secret = os.getenv("WEBHOOK_SECRET")
    if not webhook_secret:
        webhook_secret = secrets.token_urlsafe(32)
    temp_bot = Bot(token=config.TOKEN)
    await temp_bot.delete_webhook(drop_pending_updates=True)
    await temp_bot.set_webhook(
        url=webhook_url,
        secret_token=webhook_secret,
        allowed_updates=["message", "callback_query"]
    )
    await temp_bot.session.close()
    return f"✅ Вебхук успешно установлен на:\n{webhook_url}\nСекретный токен: `{webhook_secret}`"
