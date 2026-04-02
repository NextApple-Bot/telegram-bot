from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import math

from bot.db import get_pool
from bot.repositories import ClientRepository

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_clients(
    request: Request,
    search: str = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=5, le=100)
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if search:
            # Поиск с пагинацией
            offset = (page - 1) * per_page
            rows = await conn.fetch('''
                SELECT * FROM clients 
                WHERE full_name ILIKE $1 OR phone ILIKE $1 OR telegram_username ILIKE $1
                ORDER BY id DESC
                LIMIT $2 OFFSET $3
            ''', f'%{search}%', per_page, offset)
            count_row = await conn.fetchrow('''
                SELECT COUNT(*) as total FROM clients 
                WHERE full_name ILIKE $1 OR phone ILIKE $1 OR telegram_username ILIKE $1
            ''', f'%{search}%')
            total = count_row['total']
        else:
            offset = (page - 1) * per_page
            rows = await conn.fetch('''
                SELECT * FROM clients ORDER BY id DESC LIMIT $1 OFFSET $2
            ''', per_page, offset)
            count_row = await conn.fetchrow('SELECT COUNT(*) as total FROM clients')
            total = count_row['total']

        clients = [dict(row) for row in rows]

    total_pages = math.ceil(total / per_page)
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients,
        "search": search,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages
    })
