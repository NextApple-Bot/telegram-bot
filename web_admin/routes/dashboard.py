# Файл: web_admin/routes/dashboard.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
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


async def get_stats_for_date(target_date: date):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Финансы за день
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

        # Продажи (количество)
        sales_count = await conn.fetchval(
            'SELECT COALESCE(SUM(count), 0) FROM sales WHERE DATE(sold_at) = $1', target_date
        )

        # Предзаказы (количество записей)
        preorders_count = await conn.fetchval(
            'SELECT COUNT(*) FROM preorders WHERE DATE(created_at) = $1', target_date
        )

        # Брони (количество записей)
        bookings_count = await conn.fetchval(
            'SELECT COUNT(*) FROM bookings WHERE DATE(booked_at) = $1', target_date
        )

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "payments": payments,
        "total_revenue": total_revenue,
        "sales_count": sales_count,
        "preorders_count": preorders_count,
        "bookings_count": bookings_count,
    }


async def get_previous_period_stats():
    """Сравнение с вчера и прошлой неделей (для сегодня)."""
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
            target = datetime.strptime(target_date, "%Y-%m-%d").date()
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

    # Графики за 7 дней (всегда от target_date-6)
    start_date = target - timedelta(days=6)
    pool = await get_pool()
    async with pool.acquire() as conn:
        sales_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day, COALESCE(SUM(count), 0) as count
            FROM sales
            WHERE sold_at >= $1 AND sold_at <= $2
            GROUP BY day
            ORDER BY day
        ''', start_date, target)
        sales_dict = {row['day'].isoformat(): row['count'] for row in sales_rows}
        dates = [(start_date + timedelta(days=i)).isoformat() for i in range(7)]
        sales_counts = [sales_dict.get(d, 0) for d in dates]

        revenue_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day,
                   COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as revenue
            FROM sales
            WHERE sold_at >= $1 AND sold_at <= $2
            GROUP BY day
            ORDER BY day
        ''', start_date, target)
        revenue_dict = {row['day'].isoformat(): float(row['revenue']) for row in revenue_rows}
        revenue_counts = [revenue_dict.get(d, 0) for d in dates]

    # Топ-5 моделей за период days (как и раньше)
    top_cache_key = f"dashboard:top_models:{days}:{target.isoformat()}"
    cached_top = await cache.get(top_cache_key)
    if cached_top:
        top_labels, top_counts = cached_top
    else:
        period_start = target - timedelta(days=days - 1)
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT i.text
                FROM sales s
                JOIN items i ON s.item_id = i.id
                WHERE s.sold_at >= $1 AND s.sold_at <= $2 AND i.text IS NOT NULL
            ''', period_start, target)
        model_counter = Counter()
        for row in rows:
            base = extract_base_model(row['text'])
            if base:
                model_counter[base] += 1
        top_5 = model_counter.most_common(5)
        top_labels = [item[0] for item in top_5]
        top_counts = [item[1] for item in top_5]
        await cache.set(top_cache_key, (top_labels, top_counts), ttl=43200)

    # Сравнение с предыдущим периодом показываем только для сегодня
    if target == today:
        prev_stats = await get_previous_period_stats()
        sales_change_yesterday = 0
        if prev_stats['sales_yesterday']:
            sales_change_yesterday = (sales_today - prev_stats['sales_yesterday']) / prev_stats['sales_yesterday'] * 100
        revenue_change_yesterday = 0
        if prev_stats['revenue_yesterday']:
            revenue_change_yesterday = (total_revenue - prev_stats['revenue_yesterday']) / prev_stats['revenue_yesterday'] * 100
        sales_change_week = 0
        if prev_stats['sales_last_week']:
            sales_change_week = (sales_today - prev_stats['sales_last_week'] / 7) / (prev_stats['sales_last_week'] / 7) * 100
        revenue_change_week = 0
        if prev_stats['revenue_last_week']:
            revenue_change_week = (total_revenue - prev_stats['revenue_last_week'] / 7) / (prev_stats['revenue_last_week'] / 7) * 100
    else:
        sales_change_yesterday = None
        revenue_change_yesterday = None
        sales_change_week = None
        revenue_change_week = None

    response = templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": {
            "date": target.strftime("%Y-%m-%d"),
            "sales_count": sales_today,
            "preorders_count": preorders_count,
            "bookings_count": bookings_count,
        },
        "payments": payments,
        "total_revenue": total_revenue,
        "plan_amount": 600000,
        "chart_dates": dates,
        "chart_sales": sales_counts,
        "chart_revenue": revenue_counts,
        "top_labels": top_labels,
        "top_counts": top_counts,
        "days": days,
        "target_date": target.strftime("%Y-%m-%d"),
        "sales_today": sales_today,
        "revenue_today": total_revenue,
        "sales_change_yesterday": round(sales_change_yesterday, 1) if sales_change_yesterday is not None else None,
        "revenue_change_yesterday": round(revenue_change_yesterday, 1) if revenue_change_yesterday is not None else None,
        "sales_change_week": round(sales_change_week, 1) if sales_change_week is not None else None,
        "revenue_change_week": round(revenue_change_week, 1) if revenue_change_week is not None else None,
    })
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@router.get("/top_models_data")
async def top_models_data(days: int = Query(7, ge=7, le=90)):
    cache_key = f"dashboard:top_models:{days}:{date.today().isoformat()}"
    cached = await cache.get(cache_key)
    if cached:
        labels, counts = cached
        return JSONResponse(content={"labels": labels, "counts": counts})
    pool = await get_pool()
    period_start = date.today() - timedelta(days=days - 1)
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT i.text
            FROM sales s
            JOIN items i ON s.item_id = i.id
            WHERE s.sold_at >= $1 AND i.text IS NOT NULL
        ''', period_start)
    model_counter = Counter()
    for row in rows:
        base = extract_base_model(row['text'])
        if base:
            model_counter[base] += 1
    top_5 = model_counter.most_common(5)
    labels = [item[0] for item in top_5]
    counts = [item[1] for item in top_5]
    await cache.set(cache_key, (labels, counts), ttl=43200)
    return JSONResponse(content={"labels": labels, "counts": counts})


class UpdateStatsRequest(BaseModel):
    target_date: str  # YYYY-MM-DD
    cash: float = 0.0
    terminal: float = 0.0
    qr: float = 0.0
    transfer: float = 0.0
    invoice: float = 0.0
    installment: float = 0.0
    sales_count: int = 0
    preorders_count: int = 0
    bookings_count: int = 0


@router.post("/update_stats")
async def update_stats(data: UpdateStatsRequest):
    pool = await get_pool()
    target_date = datetime.strptime(data.target_date, "%Y-%m-%d").date()
    try:
        total_payments = data.cash + data.terminal + data.qr + data.transfer + data.invoice + data.installment
        if total_payments > 0 and data.sales_count == 0:
            data.sales_count = 1

        async with pool.acquire() as conn:
            async with conn.transaction():
                # Удаляем старые записи за этот день
                await conn.execute("DELETE FROM daily_payments WHERE DATE(created_at) = $1", target_date)
                await conn.execute("DELETE FROM sales WHERE DATE(sold_at) = $1", target_date)
                await conn.execute("DELETE FROM preorders WHERE DATE(created_at) = $1", target_date)
                await conn.execute("DELETE FROM bookings WHERE DATE(booked_at) = $1", target_date)

                payment_types = ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']
                for pt in payment_types:
                    amount = getattr(data, pt)
                    if amount > 0:
                        await conn.execute("""
                            INSERT INTO daily_payments (type, payment_type, amount, created_at)
                            VALUES ('sale', $1, $2, $3)
                        """, pt, amount, target_date)

                if data.sales_count > 0:
                    await conn.execute("""
                        INSERT INTO sales (count, cash, terminal, qr, transfer, invoice, installment, sold_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """, data.sales_count, data.cash, data.terminal, data.qr,
                        data.transfer, data.invoice, data.installment, target_date)

                for _ in range(data.preorders_count):
                    await conn.execute("""
                        INSERT INTO preorders (cash, terminal, qr, transfer, invoice, installment, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """, 0, 0, 0, 0, 0, 0, target_date)

                for _ in range(data.bookings_count):
                    await conn.execute("""
                        INSERT INTO bookings (item_id, total_amount, booked_at)
                        VALUES (0, 0, $1)
                    """, target_date)

        logger.info(f"Статистика за {target_date} обновлена: {data.dict()}")
        return JSONResponse({"success": True})
    except Exception as e:
        logger.exception("Ошибка при обновлении статистики")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
