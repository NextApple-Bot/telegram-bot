from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta

from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def stats_page(request: Request, days: int = Query(7, ge=1, le=90)):
    """
    Страница статистики с графиками.
    Параметр days (1-90) – количество дней для отображения.
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Получаем данные по продажам
        sales_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day, COUNT(*) as count, COALESCE(SUM(cash + terminal + qr + transfer + invoice + installment), 0) as revenue
            FROM sales
            WHERE sold_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)

        # Предзаказы
        pre_rows = await conn.fetch('''
            SELECT DATE(created_at) as day, COUNT(*) as count, COALESCE(SUM(cash + terminal + qr + transfer + invoice + installment), 0) as revenue
            FROM preorders
            WHERE created_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)

        # Брони
        book_rows = await conn.fetch('''
            SELECT DATE(booked_at) as day, COUNT(*) as count, COALESCE(SUM(total_amount), 0) as revenue
            FROM bookings
            WHERE booked_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)

    # Формируем список всех дней в диапазоне (для оси X)
    dates = [(start_date + timedelta(days=i)).isoformat() for i in range(days)]

    # Преобразуем строки в словари для быстрого доступа
    sales_dict = {row['day'].isoformat(): {'count': row['count'], 'revenue': float(row['revenue'])} for row in sales_rows}
    pre_dict   = {row['day'].isoformat(): {'count': row['count'], 'revenue': float(row['revenue'])} for row in pre_rows}
    book_dict  = {row['day'].isoformat(): {'count': row['count'], 'revenue': float(row['revenue'])} for row in book_rows}

    # Готовим данные для графиков
    sales_counts = [sales_dict.get(d, {}).get('count', 0) for d in dates]
    pre_counts   = [pre_dict.get(d, {}).get('count', 0) for d in dates]
    book_counts  = [book_dict.get(d, {}).get('count', 0) for d in dates]

    sales_revenue = [sales_dict.get(d, {}).get('revenue', 0) for d in dates]
    pre_revenue   = [pre_dict.get(d, {}).get('revenue', 0) for d in dates]
    book_revenue  = [book_dict.get(d, {}).get('revenue', 0) for d in dates]

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "dates": dates,
        "sales_counts": sales_counts,
        "pre_counts": pre_counts,
        "book_counts": book_counts,
        "sales_revenue": sales_revenue,
        "pre_revenue": pre_revenue,
        "book_revenue": book_revenue,
        "days": days
    })
