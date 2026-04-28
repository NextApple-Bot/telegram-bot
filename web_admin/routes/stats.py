# Файл: web_admin/routes/stats.py
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.db import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


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
    days: int = Query(7, ge=7, le=90),
    target_date: str | None = Query(None),
    month: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    today = date.today()
    start_date = None
    end_date = None

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

    else:
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
        end_date = start_date

    pool = await get_pool()
    async with pool.acquire() as conn:
        pay_rows = await conn.fetch('''
            SELECT payment_type, SUM(amount) as total
            FROM daily_payments
            WHERE DATE(created_at) >= $1 AND DATE(created_at) <= $2
            GROUP BY payment_type
        ''', start_date, end_date)

        sales_count = await conn.fetchval(
            'SELECT COALESCE(SUM(count), 0) FROM sales WHERE sold_at >= $1 AND sold_at <= $2',
            start_date, end_date
        )
        preorders_count = await conn.fetchval(
            'SELECT COUNT(*) FROM preorders WHERE created_at >= $1 AND created_at <= $2',
            start_date, end_date
        )
        bookings_count = await conn.fetchval(
            'SELECT COUNT(*) FROM bookings WHERE booked_at >= $1 AND booked_at <= $2',
            start_date, end_date
        )

        rev_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day,
                   COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as revenue
            FROM sales
            WHERE sold_at >= $1 AND sold_at <= $2
            GROUP BY day ORDER BY day
        ''', start_date, end_date)

    payment_labels = []
    payment_values = []
    for row in pay_rows:
        pt = row['payment_type']
        payment_labels.append({
            'cash': 'Наличные', 'terminal': 'Терминал', 'qr': 'QR-код',
            'transfer': 'Перевод', 'invoice': 'По счёту', 'installment': 'Рассрочка'
        }.get(pt, pt))
        payment_values.append(float(row['total']))

    num_days = (end_date - start_date).days + 1
    rev_dict = {row['day']: float(row['revenue']) for row in rev_rows}
    chart_dates = [(start_date + timedelta(days=i)).strftime("%d.%m.%y") for i in range(num_days)]
    chart_revenue = [rev_dict.get(start_date + timedelta(days=i), 0.0) for i in range(num_days)]

    current_month = f"{start_date.year}-{start_date.month:02d}"

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "mode": mode,
        "days": days,
        "target_date": end_date.strftime("%Y-%m-%d") if mode == "preset" else "",
        "current_month": current_month,
        "date_from": start_date.strftime("%Y-%m-%d") if mode == "range" else "",
        "date_to": end_date.strftime("%Y-%m-%d") if mode == "range" else "",
        "sales_count": sales_count,
        "preorders_count": preorders_count,
        "bookings_count": bookings_count,
        "payment_labels": payment_labels,
        "payment_values": payment_values,
        "chart_dates": chart_dates,
        "chart_revenue": chart_revenue,
    })
