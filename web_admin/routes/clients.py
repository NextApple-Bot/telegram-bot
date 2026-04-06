# Файл: web_admin/routes/clients.py
from fastapi import APIRouter, Request, Query, HTTPException, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import Optional
import csv
import io

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
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    pool = await get_pool()
    offset = (page - 1) * per_page

    base_query = "SELECT * FROM clients WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM clients WHERE 1=1"
    params = []
    count_params = []

    if search:
        base_query += " AND (full_name ILIKE $" + str(len(params)+1) + " OR phone ILIKE $" + str(len(params)+1) + " OR telegram_username ILIKE $" + str(len(params)+1) + ")"
        count_query += " AND (full_name ILIKE $" + str(len(count_params)+1) + " OR phone ILIKE $" + str(len(count_params)+1) + " OR telegram_username ILIKE $" + str(len(count_params)+1) + ")"
        params.append(f"%{search}%")
        count_params.append(f"%{search}%")

    if date_from:
        try:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
            base_query += " AND created_at >= $" + str(len(params)+1)
            count_query += " AND created_at >= $" + str(len(count_params)+1)
            params.append(start_date)
            count_params.append(start_date)
        except ValueError:
            pass

    if date_to:
        try:
            end_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            base_query += " AND created_at < $" + str(len(params)+1)
            count_query += " AND created_at < $" + str(len(count_params)+1)
            params.append(end_date)
            count_params.append(end_date)
        except ValueError:
            pass

    base_query += " ORDER BY id DESC LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
    params.append(per_page)
    params.append(offset)

    async with pool.acquire() as conn:
        total = await conn.fetchval(count_query, *count_params)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        rows = await conn.fetch(base_query, *params)
        clients = [dict(row) for row in rows]

    return templates.TemplateResponse("clients.html", {
        "request": request,
        "clients": clients,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total,
        "search": search,
        "date_from": date_from,
        "date_to": date_to,
    })


@router.get("/export/csv")
async def export_clients_csv(
    request: Request,
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    pool = await get_pool()
    query = "SELECT * FROM clients WHERE 1=1"
    params = []

    if search:
        query += " AND (full_name ILIKE $" + str(len(params)+1) + " OR phone ILIKE $" + str(len(params)+1) + " OR telegram_username ILIKE $" + str(len(params)+1) + ")"
        params.append(f"%{search}%")

    if date_from:
        try:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
            query += " AND created_at >= $" + str(len(params)+1)
            params.append(start_date)
        except ValueError:
            pass

    if date_to:
        try:
            end_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query += " AND created_at < $" + str(len(params)+1)
            params.append(end_date)
        except ValueError:
            pass

    query += " ORDER BY id"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'ФИО', 'Основной телефон', 'Все телефоны', 'Telegram', 'Соцсети', 'Источник', 'Дата регистрации', 'Дата обновления'])
    for row in rows:
        writer.writerow([
            row['id'],
            row['full_name'] or '',
            row['phone'] or '',
            row['phones'] or '',
            row['telegram_username'] or '',
            row['social_network'] or '',
            row['referral_source'] or '',
            row['created_at'].isoformat() if row['created_at'] else '',
            row['updated_at'].isoformat() if row['updated_at'] else ''
        ])

    response = StreamingResponse(iter([output.getvalue().encode('utf-8-sig')]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=clients_export.csv"
    return response


@router.get("/{client_id}", response_class=HTMLResponse)
async def client_detail(request: Request, client_id: int):
    """Страница просмотра клиента с его покупками."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        client = await conn.fetchrow('SELECT * FROM clients WHERE id = $1', client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        purchases = await conn.fetch('SELECT * FROM purchases WHERE client_id = $1 ORDER BY created_at DESC', client_id)
    return templates.TemplateResponse("client_detail.html", {
        "request": request,
        "client": dict(client),
        "purchases": [dict(p) for p in purchases]
    })


@router.get("/{client_id}/edit", response_class=HTMLResponse)
async def client_edit_form(request: Request, client_id: int):
    """Форма редактирования клиента."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        client = await conn.fetchrow('SELECT * FROM clients WHERE id = $1', client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
    return templates.TemplateResponse("client_edit.html", {
        "request": request,
        "client": dict(client)
    })


@router.post("/{client_id}/edit")
async def client_edit_submit(
    request: Request,
    client_id: int,
    full_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    phones: Optional[str] = Form(None),
    telegram_username: Optional[str] = Form(None),
    social_network: Optional[str] = Form(None),
    referral_source: Optional[str] = Form(None),
):
    """Сохраняет изменения клиента."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        updates = []
        params = []
        if full_name is not None:
            updates.append("full_name = $" + str(len(params)+1))
            params.append(full_name)
        if phone is not None:
            updates.append("phone = $" + str(len(params)+1))
            params.append(phone)
        if phones is not None:
            updates.append("phones = $" + str(len(params)+1))
            params.append(phones)
        if telegram_username is not None:
            updates.append("telegram_username = $" + str(len(params)+1))
            params.append(telegram_username)
        if social_network is not None:
            updates.append("social_network = $" + str(len(params)+1))
            params.append(social_network)
        if referral_source is not None:
            updates.append("referral_source = $" + str(len(params)+1))
            params.append(referral_source)
        if not updates:
            return RedirectResponse(url=f"/admin/clients/{client_id}", status_code=303)
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(client_id)
        query = f"UPDATE clients SET {', '.join(updates)} WHERE id = ${len(params)}"
        await conn.execute(query, *params)
    return RedirectResponse(url=f"/admin/clients/{client_id}", status_code=303)


@router.post("/delete/{client_id}")
async def delete_client(request: Request, client_id: int):
    """Удаляет клиента и все его покупки."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('DELETE FROM purchases WHERE client_id = $1', client_id)
            await conn.execute('DELETE FROM clients WHERE id = $1', client_id)
    return RedirectResponse(url="/admin/clients", status_code=303)
