from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_purchases(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    offset = (page - 1) * per_page
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT p.*, c.full_name as client_name
            FROM purchases p
            LEFT JOIN clients c ON p.client_id = c.id
            ORDER BY p.created_at DESC
            LIMIT $1 OFFSET $2
        ''', per_page, offset)
        total = await conn.fetchval('SELECT COUNT(*) FROM purchases')
        purchases = [dict(row) for row in rows]
    total_pages = (total + per_page - 1) // per_page
    return templates.TemplateResponse("purchases.html", {
        "request": request,
        "purchases": purchases,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page
    })
