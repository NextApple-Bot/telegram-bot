# Файл: web_admin/routes/purchases.py
from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from bot.db import get_pool
from web_admin.templates import templates

router = APIRouter()


@router.get("/")
async def list_purchases(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    client_search: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    payment_type: str = Query("all"),
    purchase_type: str = Query("all"),
    sort_by: str = Query("id", regex="^(id|client_name|created_at|total_amount|purchase_type)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
):
    pool = await get_pool()
    offset = (page - 1) * per_page

    base_query = """SELECT p.*, c.full_name as client_name FROM purchases p LEFT JOIN clients c ON p.client_id = c.id WHERE 1=1"""
    count_query = "SELECT COUNT(*) FROM purchases p LEFT JOIN clients c ON p.client_id = c.id WHERE 1=1"
    params = []
    count_params = []

    if client_search:
        clause = " AND (c.full_name ILIKE $" + str(len(params)+1) + " OR c.phone ILIKE $" + str(len(params)+1) + ")"
        base_query += clause
        count_query += clause
        params.append(f"%{client_search}%")
        count_params.append(f"%{client_search}%")

    if date_from:
        base_query += " AND p.created_at >= $" + str(len(params)+1)
        count_query += " AND p.created_at >= $" + str(len(count_params)+1)
        params.append(date_from)
        count_params.append(date_from)

    if date_to:
        base_query += " AND p.created_at <= $" + str(len(params)+1)
        count_query += " AND p.created_at <= $" + str(len(count_params)+1)
        params.append(date_to)
        count_params.append(date_to)

    if purchase_type != "all":
        base_query += " AND p.purchase_type = $" + str(len(params)+1)
        count_query += " AND p.purchase_type = $" + str(len(count_params)+1)
        params.append(purchase_type)
        count_params.append(purchase_type)

    allowed_sort = {"id": "p.id", "client_name": "c.full_name", "created_at": "p.created_at", "total_amount": "p.total_amount", "purchase_type": "p.purchase_type"}
    sort_col = allowed_sort.get(sort_by, "p.id")
    order_dir = "DESC" if sort_order == "desc" else "ASC"
    base_query += f" ORDER BY {sort_col} {order_dir} LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
    params.append(per_page)
    params.append(offset)

    async with pool.acquire() as conn:
        total = await conn.fetchval(count_query, *count_params)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        rows = await conn.fetch(base_query, *params)
        purchases = [dict(r) for r in rows]

    return templates.TemplateResponse("purchases.html", {
        "request": request,
        "purchases": purchases,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "client_search": client_search,
        "date_from": date_from,
        "date_to": date_to,
        "payment_type": payment_type,
        "purchase_type": purchase_type,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "payment_types": ["cash", "terminal", "qr", "transfer", "invoice", "installment"],
        "purchase_types": ["sale", "preorder", "booking"],
    })


@router.post("/delete/{purchase_id}")
async def delete_purchase(purchase_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM purchases WHERE id = $1", purchase_id)
    return RedirectResponse(url="/admin/purchases", status_code=303)


@router.get("/export/csv")
async def export_csv(request: Request):
    return RedirectResponse(url="/admin/purchases")
