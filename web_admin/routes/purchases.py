from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import math

from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_purchases(
    request: Request,
    client_id: int = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=5, le=100)
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        offset = (page - 1) * per_page
        if client_id:
            rows = await conn.fetch('''
                SELECT p.*, c.full_name as client_name
                FROM purchases p
                LEFT JOIN clients c ON p.client_id = c.id
                WHERE p.client_id = $1
                ORDER BY p.created_at DESC
                LIMIT $2 OFFSET $3
            ''', client_id, per_page, offset)
            count_row = await conn.fetchrow('SELECT COUNT(*) as total FROM purchases WHERE client_id = $1', client_id)
            total = count_row['total']
        else:
            rows = await conn.fetch('''
                SELECT p.*, c.full_name as client_name
                FROM purchases p
                LEFT JOIN clients c ON p.client_id = c.id
                ORDER BY p.created_at DESC
                LIMIT $1 OFFSET $2
            ''', per_page, offset)
            count_row = await conn.fetchrow('SELECT COUNT(*) as total FROM purchases')
            total = count_row['total']
        purchases = [dict(row) for row in rows]

    total_pages = math.ceil(total / per_page)
    return templates.TemplateResponse("purchases.html", {
        "request": request,
        "purchases": purchases,
        "client_id": client_id,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages
    })
