# Файл: web_admin/routes/clients.py
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse

from bot.db import get_pool
from bot.repositories import ClientRepository
from web_admin.templates import templates

router = APIRouter()


@router.get("/")
async def list_clients(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    sort_by: str = Query("id", regex="^(id|full_name|phone|telegram_username|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
):
    pool = await get_pool()
    offset = (page - 1) * per_page

    base_query = "SELECT * FROM clients WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM clients WHERE 1=1"
    params = []
    count_params = []

    if search:
        clause = " AND (full_name ILIKE $" + str(len(params)+1) + " OR phone ILIKE $" + str(len(params)+1) + " OR telegram_username ILIKE $" + str(len(params)+1) + ")"
        base_query += clause
        count_query += clause
        params.append(f"%{search}%")
        count_params.append(f"%{search}%")

    if date_from:
        base_query += " AND created_at >= $" + str(len(params)+1)
        count_query += " AND created_at >= $" + str(len(count_params)+1)
        params.append(date_from)
        count_params.append(date_from)

    if date_to:
        base_query += " AND created_at <= $" + str(len(params)+1)
        count_query += " AND created_at <= $" + str(len(count_params)+1)
        params.append(date_to)
        count_params.append(date_to)

    allowed_sort = {"id": "id", "full_name": "full_name", "phone": "phone", "telegram_username": "telegram_username", "created_at": "created_at"}
    sort_column = allowed_sort.get(sort_by, "id")
    order_dir = "DESC" if sort_order == "desc" else "ASC"
    base_query += f" ORDER BY {sort_column} {order_dir} LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
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
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "search": search,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort_by,
        "sort_order": sort_order,
    })


@router.get("/{client_id}")
async def client_detail(request: Request, client_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        client = await conn.fetchrow("SELECT * FROM clients WHERE id = $1", client_id)
        if not client:
            return RedirectResponse(url="/admin/clients")
        client = dict(client)
        purchases = await ClientRepository.get_client_purchases(client_id)
    return templates.TemplateResponse("client_detail.html", {
        "request": request,
        "client": client,
        "purchases": purchases,
    })


@router.get("/{client_id}/edit")
async def edit_client_form(request: Request, client_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        client = await conn.fetchrow("SELECT * FROM clients WHERE id = $1", client_id)
        if not client:
            return RedirectResponse(url="/admin/clients")
    return templates.TemplateResponse("client_edit.html", {
        "request": request,
        "client": dict(client),
    })


@router.post("/{client_id}/edit")
async def edit_client_submit(
    request: Request,
    client_id: int,
    full_name: str = Form(""),
    phone: str = Form(""),
    phones: str = Form(""),
    telegram_username: str = Form(""),
    social_network: str = Form(""),
    referral_source: str = Form(""),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE clients SET full_name=$1, phone=$2, phones=$3, telegram_username=$4,
            social_network=$5, referral_source=$6, updated_at=CURRENT_TIMESTAMP
            WHERE id=$7
        """, full_name, phone, phones, telegram_username, social_network, referral_source, client_id)
    return RedirectResponse(url=f"/admin/clients/{client_id}", status_code=303)


@router.post("/delete/{client_id}")
async def delete_client(client_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM clients WHERE id = $1", client_id)
    return RedirectResponse(url="/admin/clients", status_code=303)


@router.get("/export/csv")
async def export_clients_csv(request: Request):
    # заглушка
    return RedirectResponse(url="/admin/clients")
