from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from bot.db import get_pool
from bot.repositories import ClientRepository

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_clients(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: Optional[str] = Query(None),
):
    pool = await get_pool()
    offset = (page - 1) * per_page

    # Базовый запрос
    if search:
        # Используем поиск через репозиторий (он возвращает список без пагинации)
        # Лучше сделать отдельный запрос с пагинацией
        count_query = """
            SELECT COUNT(*) FROM clients 
            WHERE full_name ILIKE $1 OR phone ILIKE $1 OR telegram_username ILIKE $1
        """
        data_query = """
            SELECT * FROM clients 
            WHERE full_name ILIKE $1 OR phone ILIKE $1 OR telegram_username ILIKE $1
            ORDER BY id DESC
            LIMIT $2 OFFSET $3
        """
        search_pattern = f"%{search}%"
        async with pool.acquire() as conn:
            total = await conn.fetchval(count_query, search_pattern)
            rows = await conn.fetch(data_query, search_pattern, per_page, offset)
            clients = [dict(row) for row in rows]
    else:
        count_query = "SELECT COUNT(*) FROM clients"
        data_query = "SELECT * FROM clients ORDER BY id DESC LIMIT $1 OFFSET $2"
        async with pool.acquire() as conn:
            total = await conn.fetchval(count_query)
            rows = await conn.fetch(data_query, per_page, offset)
            clients = [dict(row) for row in rows]

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total,
        "search": search,
    })

@router.get("/{client_id}", response_class=HTMLResponse)
async def client_detail(request: Request, client_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        client_row = await conn.fetchrow('SELECT * FROM clients WHERE id = $1', client_id)
        if not client_row:
            return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
        client = dict(client_row)
        purchases = await ClientRepository.get_client_purchases(client_id)
    return templates.TemplateResponse("client_detail.html", {"request": request, "client": client, "purchases": purchases})
