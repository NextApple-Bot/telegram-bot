from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta

from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def stats_page(request: Request, days: int = Query(7, ge=1, le=90)):
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Продажи по дням
        sales_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day, COUNT(*) as count,
                   COALESCE(SUM(cash + terminal + qr + transfer + invoice + installment), 0) as revenue
            FROM sales
            WHERE sold_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)
        # Предзаказы по дням
        pre_rows = await conn.fetch('''
            SELECT DATE(created_at) as day, COUNT(*) as count,
                   COALESCE(SUM(cash + terminal + qr + transfer + invoice + installment), 0) as revenue
            FROM preorders
            WHERE created_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)
        # Брони по дням
        book_rows = await conn.fetch('''
            SELECT DATE(booked_at) as day, COUNT(*) as count,
                   COALESCE(SUM(total_amount), 0) as revenue
            FROM bookings
            WHERE booked_at >= $1
            GROUP BY day
            ORDER BY day
        ''', start_date)

    # Словари для быстрого доступа по дате
    sales_dict = {row['day'].isoformat(): {'count': row['count'], 'revenue': float(row['revenue'])} for row in sales_rows}
    pre_dict = {row['day'].isoformat(): {'count': row['count'], 'revenue': float(row['revenue'])} for row in pre_rows}
    book_dict = {row['day'].isoformat(): {'count': row['count'], 'revenue': float(row['revenue'])} for row in book_rows}

    # Генерируем список дат
    dates = [(start_date + timedelta(days=i)).isoformat() for i in range(days)]

    # Массивы для графиков
    sales_counts = [sales_dict.get(d, {}).get('count', 0) for d in dates]
    pre_counts = [pre_dict.get(d, {}).get('count', 0) for d in dates]
    book_counts = [book_dict.get(d, {}).get('count', 0) for d in dates]

    # Итоговые суммы
    total_sales_count = sum(sales_counts)
    total_pre_count = sum(pre_counts)
    total_book_count = sum(book_counts)
    total_sales_revenue = sum(v['revenue'] for v in sales_dict.values())
    total_pre_revenue = sum(v['revenue'] for v in pre_dict.values())
    total_book_revenue = sum(v['revenue'] for v in book_dict.values())

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "dates": dates,
        "sales_counts": sales_counts,
        "pre_counts": pre_counts,
        "book_counts": book_counts,
        "total_sales_count": total_sales_count,
        "total_pre_count": total_pre_count,
        "total_book_count": total_book_count,
        "total_sales_revenue": total_sales_revenue,
        "total_pre_revenue": total_pre_revenue,
        "total_book_revenue": total_book_revenue,
        "days": days
    })
