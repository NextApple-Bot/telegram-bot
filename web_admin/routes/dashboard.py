# Файл: web_admin/routes/dashboard.py
from fastapi import APIRouter, Request, Query, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta, datetime
from collections import Counter
import re
import logging
from pydantic import BaseModel
from typing import Optional

from bot.db import get_pool
from bot.services.cache import cache

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


def extract_base_model(full_text: str) -> str:
    for sep in [',', '(', '（']:
        if sep in full_text:
            full_text = full_text.split(sep)[0]
            break
    full_text = re.sub(r'\b\d+\s*(GB|TB|ГБ|ТБ)\b', '', full_text, flags=re.IGNORECASE)
    colors = ['Black', 'White', 'Blue', 'Green', 'Yellow', 'Red', 'Purple', 'Pink',
              'Gold', 'Silver', 'Space Gray', 'Midnight', 'Starlight', 'Cream', 'Brown',
              'Rose Gold', 'Jet Black', 'Graphite', 'Sierra Blue', 'Alpine Green',
              'Deep Purple', 'Titanium', 'Desert', 'Natural', 'Sky Blue', 'Mist Blue',
              'Lavender', 'Sage', 'Cosmic Orange', 'Cloud White', 'Light Gold']
    for color in colors:
        full_text = re.sub(rf'\b{re.escape(color)}\b', '', full_text, flags=re.IGNORECASE)
    full_text = re.sub(r'\s+', ' ', full_text).strip()
    return full_text


def parse_date_any_format(date_str: str) -> date:
    for fmt in ["%Y-%m-%d", "%d.%m.%y"]:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {date_str}")


async def get_stats_for_date(target_date: date):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT payment_type, SUM(amount) as total
            FROM daily_payments
            WHERE DATE(created_at) = $1
            GROUP BY payment_type
        ''', target_date)
        payments = {row['payment_type']: float(row['total']) for row in rows}
        for pt in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']:
            payments.setdefault(pt, 0.0)
        total_revenue = sum(payments.values())

        sales_count = await conn.fetchval(
            'SELECT COALESCE(SUM(count), 0) FROM sales WHERE DATE(sold_at) = $1', target_date
        )
        preorders_count = await conn.fetchval(
            'SELECT COUNT(*) FROM preorders WHERE DATE(created_at) = $1', target_date
        )
        bookings_count = await conn.fetchval(
            'SELECT COUNT(*) FROM bookings WHERE DATE(booked_at) = $1', target_date
        )
    return {
        "date": target_date.strftime("%d.%m.%y"),
        "payments": payments,
        "total_revenue": total_revenue,
        "sales_count": sales_count,
        "preorders_count": preorders_count,
        "bookings_count": bookings_count,
    }


async def get_previous_period_stats():
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week_start = today - timedelta(days=7)
    pool = await get_pool()
    async with pool.acquire() as conn:
        sales_yesterday = await conn.fetchval(
            'SELECT COALESCE(SUM(count), 0) FROM sales WHERE DATE(sold_at) = $1', yesterday
        )
        revenue_yesterday_rows = await conn.fetch(
            '''
            SELECT COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as total
            FROM sales WHERE DATE(sold_at) = $1
            ''', yesterday
        )
        revenue_yesterday = revenue_yesterday_rows[0]['total'] if revenue_yesterday_rows else 0
        sales_last_week = await conn.fetchval(
            'SELECT COALESCE(SUM(count), 0) FROM sales WHERE sold_at >= $1 AND sold_at < $2',
            last_week_start, today
        )
        revenue_last_week_rows = await conn.fetch(
            '''
            SELECT COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as total
            FROM sales WHERE sold_at >= $1 AND sold_at < $2
            ''', last_week_start, today
        )
        revenue_last_week = revenue_last_week_rows[0]['total'] if revenue_last_week_rows else 0
    return {
        'sales_yesterday': sales_yesterday,
        'revenue_yesterday': revenue_yesterday,
        'sales_last_week': sales_last_week,
        'revenue_last_week': revenue_last_week,
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    days: int = Query(7, ge=7, le=90),
    target_date: Optional[str] = Query(None),
):
    today = date.today()
    if target_date:
        try:
            target = parse_date_any_format(target_date)
        except ValueError:
            target = today
    else:
        target = today

    stats = await get_stats_for_date(target)
    payments = stats["payments"]
    total_revenue = stats["total_revenue"]
    sales_today = stats["sales_count"]
    preorders_count = stats["preorders_count"]
    bookings_count = stats["bookings_count"]

    start_date = target - timedelta(days=6)
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ... (получение графиков пропущено для краткости, но они остаются как прежде)

    # ... (продолжение графиков, топ-моделей, сравнения с предыдущим периодом)
    # Для brevity оставим заполнители — в реальном файле они будут.

    # Загружаем продавцов и их отметки за выбранный день
    sellers_all = await conn.fetch("SELECT id, name FROM sellers ORDER BY name")
    marked_ids = set()
    if target:
        marked = await conn.fetch("SELECT seller_id FROM seller_days WHERE date = $1", target)
        marked_ids = {r['seller_id'] for r in marked}

    sellers = [{"id": s['id'], "name": s['name'], "present": s['id'] in marked_ids} for s in sellers_all]

    response = templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "payments": payments,
        "total_revenue": total_revenue,
        "plan_amount": 600000,
        "chart_dates": [],  # placeholder
        "chart_sales": [],
        "chart_revenue": [],
        "top_labels": [],
        "top_counts": [],
        "days": days,
        "target_date": target.strftime("%d.%m.%y"),
        "target_date_iso": target.strftime("%Y-%m-%d"),
        "sales_today": sales_today,
        "revenue_today": total_revenue,
        "sales_change_yesterday": None,
        "revenue_change_yesterday": None,
        "sales_change_week": None,
        "revenue_change_week": None,
        "sellers": sellers,
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# Эндпоинт для быстрого переключения отметки продавца (AJAX)
@router.post("/toggle_seller_day")
async def toggle_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    target = parse_date_any_format(target_date)
    pool = await get_pool()
    async with pool.acquire() as conn:
        # проверяем, есть ли отметка
        exists = await conn.fetchval(
            "SELECT 1 FROM seller_days WHERE seller_id = $1 AND date = $2", seller_id, target
        )
        if exists:
            await conn.execute("DELETE FROM seller_days WHERE seller_id = $1 AND date = $2", seller_id, target)
            status = "removed"
        else:
            await conn.execute("INSERT INTO seller_days (seller_id, date) VALUES ($1, $2) ON CONFLICT DO NOTHING", seller_id, target)
            status = "added"
    return JSONResponse({"success": True, "status": status})


# Остальные эндпоинты (top_models_data, update_stats) остаются без изменений.
