from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta
import json

from bot.db import get_pool
from bot.repositories import StatsRepository

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def stats_page(request: Request, days: int = Query(7, ge=1, le=90)):
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Продажи по дням
        sales_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day, COUNT(*) as count, COALESCE(SUM(cash+terminal+qr+transfer+invoice+installment),0) as revenue
            FROM sales
            WHERE sold_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)
        # Предзаказы по дням
        pre_rows = await conn.fetch('''
            SELECT DATE(created_at) as day, COUNT(*) as count, COALESCE(SUM(cash+terminal+qr+transfer+invoice+installment),0) as revenue
            FROM preorders
            WHERE created_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)
        # Брони по дням
        book_rows = await conn.fetch('''
            SELECT DATE(booked_at) as day, COUNT(*) as count, COALESCE(SUM(total_amount),0) as revenue
            FROM bookings
            WHERE booked_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)

    # Формируем словари для быстрого доступа
    sales_data = {}
    pre_data = {}
    book_data = {}
    for row in sales_rows:
        sales_data[row['day'].isoformat()] = {'count': row['count'], 'revenue': float(row['revenue'])}
    for row in pre_rows:
        pre_data[row['day'].isoformat()] = {'count': row['count'], 'revenue': float(row['revenue'])}
    for row in book_rows:
        book_data[row['day'].isoformat()] = {'count': row['count'], 'revenue': float(row['revenue'])}

    # Создаём список всех дат в диапазоне
    dates = [(start_date + timedelta(days=i)).isoformat() for i in range(days)]

    # Передаём данные для графиков в JSON
    sales_counts = [sales_data.get(d, {}).get('count', 0) for d in dates]
    pre_counts = [pre_data.get(d, {}).get('count', 0) for d in dates]
    book_counts = [book_data.get(d, {}).get('count', 0) for d in dates]

    # Также можно передать данные о выручке для другого графика
    sales_revenue = [sales_data.get(d, {}).get('revenue', 0) for d in dates]
    pre_revenue = [pre_data.get(d, {}).get('revenue', 0) for d in dates]
    book_revenue = [book_data.get(d, {}).get('revenue', 0) for d in dates]

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "dates": json.dumps(dates),
        "sales_counts": json.dumps(sales_counts),
        "pre_counts": json.dumps(pre_counts),
        "book_counts": json.dumps(book_counts),
        "sales_revenue": json.dumps(sales_revenue),
        "pre_revenue": json.dumps(pre_revenue),
        "book_revenue": json.dumps(book_revenue),
        "days": days
    })
