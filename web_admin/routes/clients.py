from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.db import get_async_session_factory
from bot.models import Client
from web_admin.templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def clients_list(request: Request):
    async_session = get_async_session_factory()
    async with async_session() as session:
        clients = (await session.execute(select(Client).order_by(Client.created_at.desc()))).scalars().all()

    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients,
        "total": len(clients),
        "page": 1,
        "per_page": 50,
        "total_pages": 1,
        "search": "",
        "date_from": "",
        "date_to": "",
        "sort_by": "id",
        "sort_order": "desc",
    })


@router.get("/export/csv")
async def export_clients_csv(request: Request):
    # Временная заглушка
    return {"detail": "Export not implemented yet"}
