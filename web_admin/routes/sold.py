# Файл: web_admin/routes/sold.py
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from bot.db import get_pool
from bot.services.assortment import AssortmentService
from web_admin.main import templates

router = APIRouter()


@router.get("/")
async def list_sold(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
):
    pool = await get_pool()
    offset = (page - 1) * per_page
    query = "SELECT * FROM deleted_items WHERE reason = 'sale_from_admin' ORDER BY deleted_at DESC LIMIT $1 OFFSET $2"
    count_query = "SELECT COUNT(*) FROM deleted_items WHERE reason = 'sale_from_admin'"

    async with pool.acquire() as conn:
        total = await conn.fetchval(count_query)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        rows = await conn.fetch(query, per_page, offset)
        items = [dict(r) for r in rows]

    return templates.TemplateResponse("sold.html", {
        "request": request,
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    })


@router.post("/restore/{item_id}")
async def restore_sold(item_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow("SELECT * FROM deleted_items WHERE id = $1", item_id)
        if row:
            await conn.execute("INSERT INTO items (text, serial, category_id, is_booked) VALUES ($1, $2, $3, $4)",
                               row["text"], row["serial"], row["category_id"], False)
            await conn.execute("DELETE FROM deleted_items WHERE id = $1", item_id)
    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/sold", status_code=303)
