# Файл: web_admin/routes/purchases.py
from fastapi import APIRouter, Request, Query, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import Optional
import csv
import io
import json

from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

ALLOWED_SORT_FIELDS = {
    "id": "p.id",
    "created_at": "p.created_at",
    "total_amount": "p.total_amount",
    "purchase_type": "p.purchase_type",
    "client_name": "c.full_name",
}

payment_types = ["cash", "terminal", "qr", "transfer", "invoice", "installment"]
purchase_types = ["sale", "preorder", "booking"]


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
    sort_by: str = Query("id", regex="^(id|created_at|total_amount|purchase_type|client_name)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
):
    pool = await get_pool()
    offset = (page - 1) * per_page

    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, "p.id")
    order_direction = "DESC" if sort_order == "desc" else "ASC"

    base_query = """
        SELECT p.*, c.full_name as client_name
        FROM purchases p
        LEFT JOIN clients c ON p.client_id = c.id
        WHERE 1=1
    """
    count_query = "SELECT COUNT(*) FROM purchases p WHERE 1=1"
    params = []
    count_params = []

    if client_search:
        base_query += " AND (c.full_name ILIKE $" + str(len(params)+1) + " OR c.phone ILIKE $" + str(len(params)+1) + ")"
        count_query += " AND (c.full_name ILIKE $" + str(len(count_params)+1) + " OR c.phone ILIKE $" + str(len(count_params)+1) + ")"
        params.append(f"%{client_search}%")
        count_params.append(f"%{client_search}%")

    if date_from:
        try:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
            base_query += " AND p.created_at >= $" + str(len(params)+1)
            count_query += " AND p.created_at >= $" + str(len(count_params)+1)
            params.append(start_date)
            count_params.append(start_date)
        except ValueError:
            pass

    if date_to:
        try:
            end_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            base_query += " AND p.created_at < $" + str(len(params)+1)
            count_query += " AND p.created_at < $" + str(len(count_params)+1)
            params.append(end_date)
            count_params.append(end_date)
        except ValueError:
            pass

    # ИСПРАВЛЕНО: числовое приведение для фильтрации по типу оплаты
    if payment_type and payment_type != "all":
        base_query += " AND COALESCE(CAST(p.payment_details->>$" + str(len(params)+1) + " AS NUMERIC), 0) != 0"
        count_query += " AND COALESCE(CAST(p.payment_details->>$" + str(len(count_params)+1) + " AS NUMERIC), 0) != 0"
        params.append(payment_type)
        count_params.append(payment_type)

    if purchase_type and purchase_type != "all":
        base_query += " AND p.purchase_type = $" + str(len(params)+1)
        count_query += " AND p.purchase_type = $" + str(len(count_params)+1)
        params.append(purchase_type)
        count_params.append(purchase_type)

    base_query += f" ORDER BY {sort_column} {order_direction} LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
    params.append(per_page)
    params.append(offset)

    async with pool.acquire() as conn:
        total = await conn.fetchval(count_query, *count_params)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        rows = await conn.fetch(base_query, *params)
        purchases = [dict(row) for row in rows]

    # Передаём параметры в шаблон для сохранения в ссылках
    query_params = request.query_params
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
        "sort_by": sort_by,
        "sort_order": sort_order,
        "query_params": query_params,
    })


@router.get("/export/csv")
async def export_purchases_csv(
    request: Request,
    client_search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    payment_type: Optional[str] = Query(None),
    purchase_type: Optional[str] = Query(None),
):
    pool = await get_pool()
    query = """
        SELECT p.*, c.full_name as client_name, c.phone as client_phone
        FROM purchases p
        LEFT JOIN clients c ON p.client_id = c.id
        WHERE 1=1
    """
    params = []

    if client_search:
        query += " AND (c.full_name ILIKE $" + str(len(params)+1) + " OR c.phone ILIKE $" + str(len(params)+1) + ")"
        params.append(f"%{client_search}%")

    if date_from:
        try:
            start_date = datetime.strptime(date_from, "%Y-%m-%d")
            query += " AND p.created_at >= $" + str(len(params)+1)
            params.append(start_date)
        except ValueError:
            pass

    if date_to:
        try:
            end_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query += " AND p.created_at < $" + str(len(params)+1)
            params.append(end_date)
        except ValueError:
            pass

    # ИСПРАВЛЕНО: числовое приведение для экспорта
    if payment_type and payment_type != "all":
        query += " AND COALESCE(CAST(p.payment_details->>$" + str(len(params)+1) + " AS NUMERIC), 0) != 0"
        params.append(payment_type)

    if purchase_type and purchase_type != "all":
        query += " AND p.purchase_type = $" + str(len(params)+1)
        params.append(purchase_type)

    query += " ORDER BY p.created_at DESC"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID покупки', 'Клиент', 'Телефон клиента', 'Дата', 'Сумма', 'Тип', 'Товары (JSON)', 'Детали оплаты (JSON)'])
    for row in rows:
        writer.writerow([
            row['id'],
            row['client_name'] or '',
            row['client_phone'] or '',
            row['created_at'].isoformat() if row['created_at'] else '',
            float(row['total_amount']) if row['total_amount'] else 0,
            row['purchase_type'] or '',
            row['items_json'] or '',
            row['payment_details'] or ''
        ])

    response = StreamingResponse(iter([output.getvalue().encode('utf-8-sig')]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=purchases_export.csv"
    return response
