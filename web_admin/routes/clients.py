from fastapi import APIRouter, Request, Query, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
import csv
import io
from datetime import datetime

from bot.db import get_pool
from bot.repositories import ClientRepository

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_clients(request: Request, search: str = Query(None), page: int = Query(1, ge=1), per_page: int = Query(50, ge=10, le=200)):
    offset = (page - 1) * per_page
    pool = await get_pool()
    async with pool.acquire() as conn:
        if search:
            count_row = await conn.fetchval('SELECT COUNT(*) FROM clients WHERE full_name ILIKE $1 OR phone ILIKE $1', f'%{search}%')
            rows = await conn.fetch('''
                SELECT * FROM clients
                WHERE full_name ILIKE $1 OR phone ILIKE $1
                ORDER BY id DESC
                LIMIT $2 OFFSET $3
            ''', f'%{search}%', per_page, offset)
        else:
            count_row = await conn.fetchval('SELECT COUNT(*) FROM clients')
            rows = await conn.fetch('SELECT * FROM clients ORDER BY id DESC LIMIT $1 OFFSET $2', per_page, offset)
        total = count_row
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        clients = [dict(row) for row in rows]
    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients,
        "search": search,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total
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

@router.get("/export/csv")
async def export_clients_csv(request: Request, search: str = Query(None)):
    """Экспорт клиентов в CSV (с учётом поиска)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if search:
            rows = await conn.fetch('''
                SELECT * FROM clients
                WHERE full_name ILIKE $1 OR phone ILIKE $1
                ORDER BY id
            ''', f'%{search}%')
        else:
            rows = await conn.fetch('SELECT * FROM clients ORDER BY id')
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'ФИО', 'Телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации'])
    for row in rows:
        writer.writerow([
            row['id'],
            row['full_name'] or '',
            row['phone'] or '',
            row['phones'] or '',
            row['telegram_username'] or '',
            row['social_network'] or '',
            row['referral_source'] or '',
            row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row['created_at'] else ''
        ])
    output.seek(0)
    filename = f"clients_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(iter([output.getvalue().encode('utf-8-sig')]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})
