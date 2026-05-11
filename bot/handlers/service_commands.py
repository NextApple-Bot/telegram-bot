import csv
import json
import logging
import os
import tempfile
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import Client, Purchase, Category, Item, Sale, DeletedItem
from bot.repositories import ClientRepository, ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.markdown import escape_markdown_v1

logger = logging.getLogger(__name__)


# ─── Экспорт данных ─────────────────────────────────────────────
async def export_clients_csv() -> str:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            result = await session.execute(select(Client).order_by(Client.id))
            rows = result.scalars().all()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
            writer = csv.writer(tmp)
            writer.writerow(['ID', 'ФИО', 'Основной телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации'])
            for row in rows:
                writer.writerow([
                    row.id, row.full_name, row.phone, row.phones,
                    row.telegram_username, row.social_network, row.referral_source,
                    row.created_at.strftime("%d.%m.%y") if row.created_at else ''
                ])
            return tmp.name
    except (SQLAlchemyError, OSError) as e:
        logger.exception("Ошибка экспорта клиентов")
        raise


async def export_purchases_csv() -> str:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            result = await session.execute(select(Purchase).order_by(Purchase.id))
            rows = result.scalars().all()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
            writer = csv.writer(tmp)
            writer.writerow(['ID покупки', 'ID клиента', 'Товары (JSON)', 'Сумма', 'Оплата (JSON)', 'Тип', 'Дата'])
            for row in rows:
                writer.writerow([row.id, row.client_id, row.items_json, row.total_amount,
                                 row.payment_details, row.purchase_type,
                                 row.created_at.strftime("%d.%m.%y") if row.created_at else ''])
            return tmp.name
    except (SQLAlchemyError, OSError) as e:
        logger.exception("Ошибка экспорта покупок")
        raise


async def get_client_info_text(query: str) -> str | None:
    try:
        clients = await ClientRepository.search_clients(query)
    except SQLAlchemyError as e:
        logger.exception("Ошибка при поиске клиента")
        raise
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
        try:
            purchases = await ClientRepository.get_client_purchases(client['id'])
        except SQLAlchemyError as e:
            logger.exception("Ошибка получения покупок клиента")
            purchases = []
        if purchases:
            text += "*Покупки:*\n"
            for p in purchases:
                p_created = p['created_at'].strftime("%d.%m.%y") if p['created_at'] else '—'
                text += f"📅 Дата покупки: {p_created}\n"
                try:
                    items = json.loads(p['items_json']) if p['items_json'] else []
                except json.JSONDecodeError:
                    items = []
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
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            q = (
                select(
                    Client.id.label("client_id"),
                    Client.full_name,
                    Client.phone,
                    Client.telegram_username,
                    Purchase.created_at,
                    Purchase.items_json,
                    Purchase.total_amount,
                    Purchase.payment_details
                )
                .outerjoin(Purchase, Client.id == Purchase.client_id)
                .order_by(Client.id, Purchase.created_at)
            )
            result = await session.execute(q)
            rows = result.all()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
            writer = csv.writer(tmp)
            writer.writerow(['ID клиента', 'ФИО', 'Телефон', 'Telegram', 'Дата покупки', 'Товары', 'Сумма', 'Способ оплаты'])
            for row in rows:
                items = json.loads(row.items_json) if row.items_json else []
                items_short = ', '.join([it.get('item_text', '')[:30] + '...' for it in items])
                p_created = row.created_at.strftime("%d.%m.%y") if row.created_at else ''
                writer.writerow([row.client_id, row.full_name, row.phone, row.telegram_username,
                                 p_created, items_short, row.total_amount, row.payment_details])
            return tmp.name
    except (SQLAlchemyError, OSError, json.JSONDecodeError) as e:
        logger.exception("Ошибка экспорта полного отчёта")
        raise


# ─── Управление категориями ─────────────────────────────────────
async def list_categories_text() -> str:
    async_session = get_async_session_factory()
    try:
        async with async_session() as session:
            q = (
                select(
                    Category.id,
                    Category.name,
                    func.count(Item.id).label("item_count")
                )
                .outerjoin(Item, Category.id == Item.category_id)
                .group_by(Category.id, Category.name)
                .order_by(Category.id)
            )
            result = await session.execute(q)
            rows = result.all()
    except SQLAlchemyError as e:
        logger.exception("Ошибка при получении списка категорий")
        raise
    text = "📋 **Список категорий:**\n\n"
    for r in rows:
        text += f"🆔 `{r.id}` — **{escape_markdown_v1(r.name)}** (товаров: {r.item_count})\n"
    return text


async def find_empty_categories() -> list[dict]:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            q = (
                select(Category.id, Category.name)
                .outerjoin(Item, Category.id == Item.category_id)
                .where(Item.id.is_(None))
            )
            result = await session.execute(q)
            rows = result.all()
        return [{"id": r.id, "name": r.name} for r in rows]
    except SQLAlchemyError as e:
        logger.exception("Ошибка при поиске пустых категорий")
        raise


async def delete_category_if_empty(cat_id: int) -> tuple[bool, str]:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            cat = await session.get(Category, cat_id)
            if not cat:
                return False, f"❌ Категория с ID {cat_id} не найдена."
            count_q = select(func.count(Item.id)).where(Item.category_id == cat_id)
            count = (await session.execute(count_q)).scalar()
            if count > 0:
                return False, f"❌ Категория «{escape_markdown_v1(cat.name)}» содержит {count} товаров. Удаление невозможно."
            return True, f"«{escape_markdown_v1(cat.name)}» (ID {cat_id})"
    except SQLAlchemyError as e:
        logger.exception("Ошибка при проверке категории на удаление")
        raise


async def merge_categories(from_id: int, to_id: int) -> tuple[bool, str]:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            from_cat = await session.get(Category, from_id)
            to_cat = await session.get(Category, to_id)
            if not from_cat or not to_cat:
                return False, "❌ Одна из категорий не найдена"
            count_q = select(func.count(Item.id)).where(Item.category_id == from_id)
            count = (await session.execute(count_q)).scalar()
            if count == 0:
                return False, f"❌ В категории «{escape_markdown_v1(from_cat.name)}» нет товаров. Удалите её через /delete_category."
            msg = f"⚠️ Перенести {count} товаров из «{escape_markdown_v1(from_cat.name)}» (ID {from_id}) в «{escape_markdown_v1(to_cat.name)}» (ID {to_id})?\nПосле этого категория {from_id} будет удалена."
            return True, msg
    except SQLAlchemyError as e:
        logger.exception("Ошибка при подготовке слияния категорий")
        raise


async def reset_assortment() -> str:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            subq = select(Category.id).where(Category.name == '__SYSTEM__')
            sys_id = (await session.execute(subq)).scalar()
            if sys_id:
                await session.execute("DELETE FROM items WHERE category_id != :sys_id", {"sys_id": sys_id})
            await session.execute("DELETE FROM categories WHERE name != '__SYSTEM__'")
        await AssortmentService.invalidate_cache()
        return "✅ Ассортимент полностью очищен"
    except SQLAlchemyError as e:
        logger.exception("Ошибка при очистке ассортимента")
        raise


# ─── Удаление по ID ─────────────────────────────────────────────
async def delete_client_by_id(client_id: int) -> tuple[bool, str]:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            client = await session.get(Client, client_id)
            if not client:
                return False, f"❌ Клиент с ID {client_id} не найден."
            count_q = select(func.count(Purchase.id)).where(Purchase.client_id == client_id)
            purchases = (await session.execute(count_q)).scalar()
            warning = f"⚠️ Удалить клиента «{escape_markdown_v1(client.full_name or 'Без имени')}» (ID {client_id})?"
            if purchases:
                warning += f"\n⚠️ У клиента есть {purchases} покупок — они будут удалены вместе с клиентом."
            return True, warning
    except SQLAlchemyError as e:
        logger.exception("Ошибка при подготовке удаления клиента")
        raise


async def delete_purchase_by_id(purchase_id: int) -> tuple[bool, str]:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            purchase = await session.get(Purchase, purchase_id)
            if not purchase:
                return False, f"❌ Покупка с ID {purchase_id} не найдена."
            return True, f"⚠️ Удалить покупку ID {purchase_id} на сумму {purchase.total_amount} ₽?"
    except SQLAlchemyError as e:
        logger.exception("Ошибка при подготовке удаления покупки")
        raise


async def undo_last_deletion() -> str:
    try:
        deleted = await ItemRepository.get_last_deleted_item()
    except SQLAlchemyError as e:
        logger.exception("Ошибка получения последнего удалённого товара")
        raise
    if not deleted:
        return "📭 Нет удалённых товаров для восстановления."
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            cat = await session.get(Category, deleted['category_id'])
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
    except SQLAlchemyError as e:
        logger.exception("Ошибка восстановления товара")
        raise


async def fix_sales_unique() -> str:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            result1 = await session.execute("DELETE FROM sales WHERE message_id IS NULL")
            deleted_null = result1.rowcount
            result2 = await session.execute(
                "DELETE FROM sales a USING sales b WHERE a.id > b.id AND a.message_id = b.message_id"
            )
            deleted_dups = result2.rowcount
            try:
                await session.execute("ALTER TABLE sales ADD CONSTRAINT sales_message_id_key UNIQUE (message_id)")
                constraint_added = True
            except SQLAlchemyError:
                constraint_added = False
        return f"✅ Исправление таблицы sales:\n• Удалено записей с NULL message_id: {deleted_null}\n• Удалено дубликатов: {deleted_dups}\n• Уникальное ограничение: {'добавлено' if constraint_added else 'уже существовало'}"
    except SQLAlchemyError as e:
        logger.exception("Ошибка исправления таблицы sales")
        raise


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
    try:
        await temp_bot.delete_webhook(drop_pending_updates=True)
        await temp_bot.set_webhook(
            url=webhook_url,
            secret_token=webhook_secret,
            allowed_updates=["message", "callback_query"]
        )
    except Exception as e:
        logger.exception("Ошибка установки вебхука вручную")
        return f"❌ Ошибка: {e}"
    finally:
        await temp_bot.session.close()
    return f"✅ Вебхук успешно установлен на:\n{webhook_url}\nСекретный токен: `{webhook_secret}`"
