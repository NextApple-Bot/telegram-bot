from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_purchases(request: Request):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT p.*, c.full_name as client_name
            FROM purchases p
            LEFT JOIN clients c ON p.client_id = c.id
            ORDER BY p.created_at DESC
            LIMIT 200
        ''')
        purchases = [dict(row) for row in rows]
    return templates.TemplateResponse("purchases.html", {"request": request, "purchases": purchases})
