# Файл: web_admin/routes/assortment/views.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import re

from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

ALLOWED_SORT_FIELDS = {
    "id": "i.id",
    "text": "i.text",
    "serial": "i.serial",
    "category_name": "c.name",
    "is_booked": "i.is_booked",
    "created_at": "i.created_at",
}


@router.get("/", response_class=HTMLResponse)
async def list_assortment(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    sort_by: str = Query("id", regex="^(id|text|serial|category_name|is_booked|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
):
    pool = await get_pool()
    offset = (page - 1) * per_page

    category_id_int = None
    if category_id and category_id.isdigit():
        category_id_int = int(category_id)

    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, "i.id")
    order_direction = "DESC" if sort_order == "desc" else "ASC"

    base_query = f"""
        SELECT i.id, i.text, i.serial, i.is_booked, i.created_at,
               c.id as category_id, c.name as category_name
        FROM items i
        JOIN categories c ON i.category_id = c.id
        WHERE 1=1
    """
    count_query = "SELECT COUNT(*) FROM items i WHERE 1=1"
    params = []
    count_params = []

    if search:
        search_condition = " AND (i.text ILIKE $" + str(len(params)+1) + " OR i.serial ILIKE $" + str(len(params)+1) + ")"
        base_query += search_condition
        count_query += search_condition
        params.append(f"%{search}%")
        count_params.append(f"%{search}%")

    if category_id_int is not None:
        base_query += " AND i.category_id = $" + str(len(params)+1)
        count_query += " AND i.category_id = $" + str(len(count_params)+1)
        params.append(category_id_int)
        count_params.append(category_id_int)

    base_query += f" ORDER BY {sort_column} {order_direction} LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
    params.append(per_page)
    params.append(offset)

    async with pool.acquire() as conn:
        total = await conn.fetchval(count_query, *count_params)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        rows = await conn.fetch(base_query, *params)
        items = [dict(row) for row in rows]
        categories_rows = await conn.fetch("SELECT id, name FROM categories ORDER BY name")
        categories = [{"id": row["id"], "name": row["name"]} for row in categories_rows]

    return templates.TemplateResponse("assortment.html", {
        "request": request,
        "items": items,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total,
        "search": search,
        "category_id": category_id,
        "categories": categories,
        "sort_by": sort_by,
        "sort_order": sort_order,
    })


@router.get("/search")
async def search_items(q: str = Query(..., min_length=2)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT i.id, i.text, i.serial, c.name as category_name
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE i.text ILIKE $1 OR i.serial ILIKE $1
            ORDER BY i.id DESC
            LIMIT 10
        ''', f'%{q}%')
    results = [{"id": r["id"], "text": r["text"], "serial": r["serial"], "category": r["category_name"]} for r in rows]
    return {"results": results}


@router.get("/api/search_by_serial")
async def search_by_serial(q: str = Query(..., min_length=1)):
    # Удаляем символ '№' и все пробелы из запроса
    normalized_q = re.sub(r'[№\s]', '', q.strip())
    if len(normalized_q) < 1:
        return {"results": []}

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT i.id, i.text, i.serial, i.sale_price,
                   c.name as category_name
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE regexp_replace(i.serial, '[№\\s]', '', 'g') ILIKE $1
            ORDER BY i.id
            LIMIT 10
        ''', f'%{normalized_q}%')
    
    results = []
    for r in rows:
        price = r['sale_price']
        if price is None:
            match = re.search(r'(\d[\d\s]*[.,]?\d*)\s*(?:₽|руб)', r['text'])
            if match:
                price_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    price = float(price_str)
                except ValueError:
                    price = None
        results.append({
            "id": r['id'],
            "text": r['text'],
            "serial": r['serial'],
            "price": price,
            "category": r['category_name']
        })
    return {"results": results}
