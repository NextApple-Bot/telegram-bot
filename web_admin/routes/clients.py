from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.db import get_pool
from bot.repositories import ClientRepository

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_clients(
    request: Request,
    search: str = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    offset = (page - 1) * per_page
    pool = await get_pool()
    async with pool.acquire() as conn:
        if search:
            # Ищем по имени, телефону, telegram
            rows = await conn.fetch('''
                SELECT * FROM clients 
                WHERE full_name ILIKE $1 OR phone ILIKE $1 OR telegram_username ILIKE $1
                ORDER BY id DESC
                LIMIT $2 OFFSET $3
            ''', f'%{search}%', per_page, offset)
            total = await conn.fetchval('''
                SELECT COUNT(*) FROM clients 
                WHERE full_name ILIKE $1 OR phone ILIKE $1 OR telegram_username ILIKE $1
            ''', f'%{search}%')
        else:
            rows = await conn.fetch('''
                SELECT * FROM clients 
                ORDER BY id DESC
                LIMIT $1 OFFSET $2
            ''', per_page, offset)
            total = await conn.fetchval('SELECT COUNT(*) FROM clients')
        clients = [dict(row) for row in rows]
    total_pages = (total + per_page - 1) // per_page
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients,
        "search": search,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page
    })
