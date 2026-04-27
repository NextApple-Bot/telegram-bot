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
    """Парсит дату из строки, поддерживая DD.MM.YY и YYYY-MM-DD."""
    for fmt in ["%Y-%m-%d", "%d.%m.%y"]:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {date_str}")

async def get_stats_for_date(target_date: date):
    """Собирает статистику продаж, предзаказов и броней за указанный день."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # --- Финансы из daily_payments (наиболее точные данные) ---
        rows = await conn.fetch('''
            SELECT payment_type, SUM(amount) as total
            FROM daily_payments
            WHERE DATE(created_at) = $1
            GROUP BY payment_type
        ''', target_date)
        payments = {row['payment_type']: float(row['total']) for row in rows}
        total_revenue = sum(payments.values())

        # --- Количество сущностей ---
        sales_count = await conn.fetchval(
            'SELECT COALESCE(SUM(count), 0) FROM sales WHERE DATE(sold_at) = $1', target_date
        )
        preorders_count = await conn.fetchval(
            'SELECT COUNT(*) FROM preorders WHERE DATE(created_at) = $1', target_date
        )
        bookings_count = await conn.fetchval(
            'SELECT COUNT(*) FROM bookings WHERE DATE(booked_at) = $1', target_date
        )

        # --- Детализация по платежам из daily_payments ---
        # Для категорий, не имеющих платежей, устанавливаем 0
        detailed_payments = {
            'cash': payments.get('cash', 0.0),
            'terminal': payments.get('terminal', 0.0),
            'qr': payments.get('qr', 0.0),
            'transfer': payments.get('transfer', 0.0),
            'invoice': payments.get('invoice', 0.0),
            'installment': payments.get('installment', 0.0),
        }

    return {
        "date": target_date.strftime("%d.%m.%y"),
        "total_revenue": total_revenue,
        "sales_count": sales_count,
        "preorders_count": preorders_count,
        "bookings_count": bookings_count,
        "detailed_payments": detailed_payments,
    }


@router.get("/", response_class=HTMLResponse)
async def stats_page(
    request: Request,
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

    try:
        stats = await get_stats_for_date(target)
    except Exception as e:
        logger.exception("Error in stats_page")
        raise HTTPException(status_code=500, detail=str(e))

    return templates.TemplateResponse("stats.html", {
        "request": request,
        "target_date": target.strftime("%d.%m.%y"),
        "target_date_iso": target.strftime("%Y-%m-%d"),
        "stats": stats,
    })
