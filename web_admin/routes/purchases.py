from fastapi import APIRouter, Request, Query, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import date, datetime, timedelta
from typing import Optional

from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_purchases(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    client_search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    payment_type: Optional[str] = Query(None),
    purchase_type: Optional[str] = Query(None),
):
    pool = await get_pool()
    offset = (page - 1) * per_page

    # Базовый запрос с JOIN для получения имени клиента
    base_query = """
        SELECT p.*, c.full_name as client_name
        FROM purchases p
        LEFT JOIN clients c ON p.client_id = c.id
        WHERE 1=1
    """
    count_query = "SELECT COUNT(*) FROM purchases p WHERE 1=1"
    params = []
    count_params = []

    # Фильтр по поиску клиента (имя или телефон)
    if client_search:
        base_query += " AND (c.full_name ILIKE $" + str(len(params)+1) + " OR c.phone ILIKE $" + str(len(params)+1) + ")"
        count_query += " AND (c.full_name ILIKE $" + str(len(count_params)+1) + " OR c.phone ILIKE $" + str(len(count_params)+1) + ")"
        params.append(f"%{client_search}%")
        count_params.append(f"%{client_search}%")

    # Фильтр по дате начала
    if date_from:
        try:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
            base_query += " AND p.created_at >= $" + str(len(params)+1)
            count_query += " AND p.created_at >= $" + str(len(count_params)+1)
            params.append(start_date)
            count_params.append(start_date)
        except ValueError:
            pass

    # Фильтр по дате окончания
    if date_to:
        try:
            end_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            base_query += " AND p.created_at < $" + str(len(params)+1)
            count_query += " AND p.created_at < $" + str(len(count_params)+1)
            params.append(end_date)
            count_params.append(end_date)
        except ValueError:
            pass

    # Фильтр по типу оплаты (проверяем payment_details JSON)
    if payment_type and payment_type != "all":
        base_query += " AND p.payment_details->>$" + str(len(params)+1) + " > '0'"
        count_query += " AND p.payment_details->>$" + str(len(count_params)+1) + " > '0'"
        params.append(payment_type)
        count_params.append(payment_type)

    # Фильтр по типу покупки
    if purchase_type and purchase_type != "all":
        base_query += " AND p.purchase_type = $" + str(len(params)+1)
        count_query += " AND p.purchase_type = $" + str(len(count_params)+1)
        params.append(purchase_type)
        count_params.append(purchase_type)

    # Сортировка и пагинация
    base_query += " ORDER BY p.created_at DESC LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
    params.append(per_page)
    params.append(offset)

    async with pool.acquire() as conn:
        # Получаем общее количество записей
        total = await conn.fetchval(count_query, *count_params)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        # Получаем записи
        rows = await conn.fetch(base_query, *params)
        purchases = [dict(row) for row in rows]

    # Для фильтра по типу оплаты нужно знать, какие типы доступны (можно вынести статически)
    payment_types = ["cash", "terminal", "qr", "transfer", "invoice", "installment"]
    purchase_types = ["sale", "preorder", "booking"]

    return templates.TemplateResponse("purchases.html", {
        "request": request,
        "purchases": purchases,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total,
        "client_search": client_search,
        "date_from": date_from,
        "date_to": date_to,
        "payment_type": payment_type,
        "purchase_type": purchase_type,
        "payment_types": payment_types,
        "purchase_types": purchase_types,
    })
