from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta, datetime
import logging
from typing import Optional

from bot.db import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

# --- ФИЛЬТР ДАТЫ ---
def _format_date(value, fmt="%d.%m.%y"):
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, str):
        for fmt_in in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
            try:
                dt = datetime.strptime(value, fmt_in)
                return dt.strftime(fmt)
            except ValueError:
                continue
    return value

templates.env.filters["format_date"] = _format_date
# -------------------

def parse_date_any_format(date_str: str) -> date:
    for fmt in ["%Y-%m-%d", "%d.%m.%y"]:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {date_str}")

@router.get("/", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    target_date: Optional[str] = Query(None),
    days: int = Query(7, ge=7, le=30),
):
    today = date.today()
    if target_date:
        try:
            target = parse_date_any_format(target_date)
        except ValueError:
            target = today
    else:
        target = today

    # Вычисляем начало периода
    start_date = target - timedelta(days=days - 1)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # --- Ежедневная статистика ---
        sales_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day, COALESCE(SUM(count), 0) as count,
                   COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as revenue
            FROM sales
            WHERE sold_at >= $1 AND sold_at <= $2
            GROUP BY day
            ORDER BY day
        ''', start_date, target)

        pre_rows = await conn.fetch('''
            SELECT DATE(created_at) as day, COUNT(*) as count,
                   COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as revenue
            FROM preorders
            WHERE created_at >= $1 AND created_at <= $2
            GROUP BY day
            ORDER BY day
        ''', start_date, target)

        book_rows = await conn.fetch('''
            SELECT DATE(booked_at) as day, COUNT(*) as count,
                   COALESCE(SUM(total_amount), 0) as revenue
            FROM bookings
            WHERE booked_at >= $1 AND booked_at <= $2
            GROUP BY day
            ORDER BY day
        ''', start_date, target)

    # Формируем списки для графиков
    dates = [(start_date + timedelta(days=i)).strftime("%d.%m.%y") for i in range(days)]
    sales_counts = []
    pre_counts = []
    book_counts = []
    revenue_vals = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        s_count = 0
        s_rev = 0.0
        for row in sales_rows:
            if row['day'] == d:
                s_count = int(row['count'])
                s_rev = float(row['revenue'])
                break
        sales_counts.append(s_count)
        revenue_vals.append(s_rev)

        p_count = 0
        for row in pre_rows:
            if row['day'] == d:
                p_count = int(row['count'])
                break
        pre_counts.append(p_count)

        b_count = 0
        for row in book_rows:
            if row['day'] == d:
                b_count = int(row['count'])
                break
        book_counts.append(b_count)

    # Итоговые суммы за период
    total_sales = sum(sales_counts)
    total_preorders = sum(pre_counts)
    total_bookings = sum(book_counts)
    total_revenue = sum(revenue_vals)

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "target_date": target.strftime("%d.%m.%y"),
        "target_date_iso": target.strftime("%Y-%m-%d"),
        "days": days,
        "dates": dates,
        "sales_counts": sales_counts,
        "pre_counts": pre_counts,
        "book_counts": book_counts,
        "revenue_vals": revenue_vals,
        "total_sales": total_sales,
        "total_preorders": total_preorders,
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
    })
