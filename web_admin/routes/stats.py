from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta, datetime
from collections import defaultdict
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
    mode: str = Query("preset", regex="^(preset|month|range)$"),
    # preset
    days: int = Query(7, ge=7, le=90),
    target_date: Optional[str] = Query(None),
    # month
    month: Optional[str] = Query(None),          # YYYY-MM
    # range
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    today = date.today()
    start_date = None
    end_date = None

    # --- Определяем период ---
    if mode == "preset":
        if target_date:
            try:
                end_date = parse_date_any_format(target_date)
            except ValueError:
                end_date = today
        else:
            end_date = today
        start_date = end_date - timedelta(days=days - 1)

    elif mode == "month":
        if month:
            try:
                y, m = map(int, month.split("-"))
                start_date = date(y, m, 1)
                if m == 12:
                    end_date = date(y + 1, 1, 1) - timedelta(days=1)
                else:
                    end_date = date(y, m + 1, 1) - timedelta(days=1)
            except (ValueError, IndexError):
                start_date = today.replace(day=1)
                end_date = today
        else:
            start_date = today.replace(day=1)
            end_date = today

    else:  # mode == "range"
        if date_from:
            try:
                start_date = parse_date_any_format(date_from)
            except ValueError:
                start_date = today - timedelta(days=7)
        else:
            start_date = today - timedelta(days=7)
        if date_to:
            try:
                end_date = parse_date_any_format(date_to)
            except ValueError:
                end_date = today
        else:
            end_date = today

    if end_date < start_date:
        end_date = start_date  # защита от дурака

    # --- Данные ---
    pool = await get_pool()
    async with pool.acquire() as conn:
        sales_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day, COALESCE(SUM(count), 0) as count,
                   COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as revenue
            FROM sales
            WHERE sold_at >= $1 AND sold_at <= $2
            GROUP BY day ORDER BY day
        ''', start_date, end_date)

        pre_rows = await conn.fetch('''
            SELECT DATE(created_at) as day, COUNT(*) as count
            FROM preorders
            WHERE created_at >= $1 AND created_at <= $2
            GROUP BY day ORDER BY day
        ''', start_date, end_date)

        book_rows = await conn.fetch('''
            SELECT DATE(booked_at) as day, COUNT(*) as count
            FROM bookings
            WHERE booked_at >= $1 AND booked_at <= $2
            GROUP BY day ORDER BY day
        ''', start_date, end_date)

    # --- Агрегация ---
    num_days = (end_date - start_date).days + 1
    use_weeks = num_days > 21

    labels = []
    sales_counts = []
    pre_counts = []
    book_counts = []
    revenue_vals = []

    if use_weeks:
        week_data = defaultdict(lambda: {"sales": 0, "pre": 0, "book": 0, "rev": 0.0})
        for row in sales_rows:
            d = row['day']
            iso = d.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
            week_data[key]["sales"] += int(row['count'])
            week_data[key]["rev"] += float(row['revenue'])
        for row in pre_rows:
            d = row['day']
            iso = d.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
            week_data[key]["pre"] += int(row['count'])
        for row in book_rows:
            d = row['day']
            iso = d.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
            week_data[key]["book"] += int(row['count'])

        sorted_keys = sorted(week_data.keys())
        labels = sorted_keys
        sales_counts = [week_data[k]["sales"] for k in sorted_keys]
        pre_counts = [week_data[k]["pre"] for k in sorted_keys]
        book_counts = [week_data[k]["book"] for k in sorted_keys]
        revenue_vals = [week_data[k]["rev"] for k in sorted_keys]
    else:
        sales_dict = {row['day']: (int(row['count']), float(row['revenue'])) for row in sales_rows}
        pre_dict = {row['day']: int(row['count']) for row in pre_rows}
        book_dict = {row['day']: int(row['count']) for row in book_rows}

        for i in range(num_days):
            d = start_date + timedelta(days=i)
            labels.append(d.strftime("%d.%m.%y"))
            sc, sr = sales_dict.get(d, (0, 0.0))
            sales_counts.append(sc)
            revenue_vals.append(sr)
            pre_counts.append(pre_dict.get(d, 0))
            book_counts.append(book_dict.get(d, 0))

    total_sales = sum(sales_counts)
    total_pre = sum(pre_counts)
    total_book = sum(book_counts)
    total_revenue = sum(revenue_vals)

    current_month = f"{start_date.year}-{start_date.month:02d}"

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "mode": mode,
        "days": days,
        "target_date": end_date.strftime("%Y-%m-%d") if mode == "preset" else "",
        "current_month": current_month,
        "date_from": start_date.strftime("%Y-%m-%d") if mode == "range" else "",
        "date_to": end_date.strftime("%Y-%m-%d") if mode == "range" else "",
        "labels": labels,
        "sales_counts": sales_counts,
        "pre_counts": pre_counts,
        "book_counts": book_counts,
        "revenue_vals": revenue_vals,
        "total_sales": total_sales,
        "total_pre": total_pre,
        "total_book": total_book,
        "total_revenue": total_revenue,
        "use_weeks": use_weeks,
    })
