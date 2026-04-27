# Файл: web_admin/routes/sold.py
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import logging
from datetime import datetime

from bot.db import get_pool
from bot.services.assortment import AssortmentService

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

# --- ФИЛЬТР ДАТЫ ---
def _format_date(value, fmt="%d.%m.%y"):
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, str):
        for fmt_in in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
            try:
                dt = datetime.strptime(value, fmt_in)
                return dt.strftime(fmt)
            except ValueError:
                continue
    return value

templates.env.filters["format_date"] = _format_date
# -------------------


@router.get("/", response_class=HTMLResponse)
async def list_sold(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
):
    pool = await get_pool()
    offset = (page - 1) * per_page

    query = """
        SELECT id, item_id, text, serial, category_id, deleted_at, sale_message_id, reason
        FROM deleted_items
        WHERE restored = FALSE
        ORDER BY deleted_at DESC
        LIMIT $1 OFFSET $2
    """
    count_query = """
        SELECT COUNT(*) FROM deleted_items
        WHERE restored = FALSE
    """

    async with pool.acquire() as conn:
        total = await conn.fetchval(count_query)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        rows = await conn.fetch(query, per_page, offset)
        items = [dict(row) for row in rows]

    return templates.TemplateResponse("sold.html", {
        "request": request,
        "items": items,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total,
    })


@router.post("/restore/{deleted_id}")
async def restore_sold(deleted_id: int, request: Request):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("""
                SELECT item_id, text, serial, category_id, sale_message_id
                FROM deleted_items
                WHERE id = $1 AND restored = FALSE
            """, deleted_id)
            if not row:
                raise HTTPException(status_code=404, detail="Запись не найдена или уже восстановлена")

            item_id = row["item_id"]
            sale_message_id = row["sale_message_id"]
            category_id = row["category_id"]

            # Проверяем существование категории
            cat_exists = await conn.fetchval("SELECT 1 FROM categories WHERE id = $1", category_id)
            if not cat_exists:
                default_cat_id = await conn.fetchval("""
                    INSERT INTO categories (name) VALUES ('Общее:')
                    ON CONFLICT (name) DO NOTHING
                    RETURNING id
                """)
                if not default_cat_id:
                    default_cat_id = await conn.fetchval("SELECT id FROM categories WHERE name = 'Общее:'")
                category_id = default_cat_id
                logger.info(f"Категория {row['category_id']} не найдена, товар восстановлен в категорию 'Общее:' (id={category_id})")

            if sale_message_id:
                await conn.execute("DELETE FROM sales WHERE message_id = $1", sale_message_id)
                await conn.execute("DELETE FROM daily_payments WHERE sale_message_id = $1", sale_message_id)
                logger.info(f"Удалены продажа и финансы для sale_message_id={sale_message_id}")
            else:
                logger.warning(f"Не найден sale_message_id для записи deleted_id={deleted_id}, статистика не удалена")

            await conn.execute("""
                INSERT INTO items (text, serial, category_id, is_booked)
                VALUES ($1, $2, $3, FALSE)
            """, row["text"], row["serial"], category_id)

            await conn.execute("""
                UPDATE deleted_items SET restored = TRUE WHERE id = $1
            """, deleted_id)

    await AssortmentService.invalidate_cache()
    logger.warning(
        "Товар восстановлен. Если была предоплата (бронь) с отдельным message_id, "
        "она не была удалена. Проверьте финансовую статистику вручную."
    )
    return RedirectResponse(url="/admin/sold", status_code=303)
