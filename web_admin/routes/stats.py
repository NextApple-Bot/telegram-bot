from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta

from bot.db import get_pool
from bot.repositories import StatsRepository

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def stats_page(request: Request, days: int = Query(7)):
    # Статистика за последние days дней
    end_date = date.today()
    start_date = end_date - timedelta(days=days-1)
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Продажи по дням
        sales_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day, COUNT(*) as count, SUM(cash+terminal+qr+transfer+invoice+installment) as revenue
            FROM sales
            WHERE sold_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)
        # Предзаказы по дням
        pre_rows = await conn.fetch('''
            SELECT DATE(created_at) as day, COUNT(*) as count, SUM(cash+terminal+qr+transfer+invoice+installment) as revenue
            FROM preorders
            WHERE created_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)
        # Брони по дням
        book_rows = await conn.fetch('''
            SELECT DATE(booked_at) as day, COUNT(*) as count, SUM(total_amount) as revenue
            FROM bookings
            WHERE booked_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)
    # Формируем данные для графика (можно передать в шаблон)
    dates = [(start_date + timedelta(days=i)).isoformat() for i in range(days)]
    sales_data = {row['day'].isoformat(): {'count': row['count'], 'revenue': float(row['revenue'])} for row in sales_rows}
    pre_data = {row['day'].isoformat(): {'count': row['count'], 'revenue': float(row['revenue'])} for row in pre_rows}
    book_data = {row['day'].isoformat(): {'count': row['count'], 'revenue': float(row['revenue'])} for row in book_rows}

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "dates": dates,
        "sales_data": sales_data,
        "pre_data": pre_data,
        "book_data": book_data,
        "days": days
    })
