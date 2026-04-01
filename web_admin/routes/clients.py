from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.repositories import ClientRepository

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_clients(request: Request, search: str = Query(None)):
    if search:
        clients = await ClientRepository.search_clients(search)
    else:
        # Получить всех клиентов – нужно добавить метод в репозиторий
        from bot.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM clients ORDER BY id DESC LIMIT 100')
            clients = [dict(row) for row in rows]
    return templates.TemplateResponse("clients.html", {"request": request, "clients": clients, "search": search})

@router.get("/{client_id}", response_class=HTMLResponse)
async def client_detail(request: Request, client_id: int):
    from bot.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        client_row = await conn.fetchrow('SELECT * FROM clients WHERE id = $1', client_id)
        if not client_row:
            return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
        client = dict(client_row)
        purchases = await ClientRepository.get_client_purchases(client_id)
    return templates.TemplateResponse("client_detail.html", {"request": request, "client": client, "purchases": purchases})
