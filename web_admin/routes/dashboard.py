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
        sales_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day, COALESCE(SUM(count), 0) as count
            FROM sales
            WHERE sold_at >= $1 AND sold_at <= $2
            GROUP BY day ORDER BY day
        ''', start_date, target)
        sales_dict = {row['day'].isoformat(): row['count'] for row in sales_rows}
        dates = [(start_date + timedelta(days=i)).strftime("%d.%m.%y") for i in range(7)]
        sales_counts = [sales_dict.get((start_date + timedelta(days=i)).isoformat(), 0) for i in range(7)]

        revenue_rows = await conn.fetch('''
            SELECT DATE(sold_at) as day,
                   COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as revenue
            FROM sales
            WHERE sold_at >= $1 AND sold_at <= $2
            GROUP BY day ORDER BY day
        ''', start_date, target)
        revenue_dict = {row['day'].isoformat(): float(row['revenue']) for row in revenue_rows}
        revenue_counts = [revenue_dict.get((start_date + timedelta(days=i)).isoformat(), 0) for i in range(7)]

        period_start = target - timedelta(days=days - 1)
        top_rows = await conn.fetch('''
            SELECT i.text
            FROM sales s
            JOIN items i ON s.item_id = i.id
            WHERE s.sold_at >= $1 AND s.sold_at <= $2 AND i.text IS NOT NULL
        ''', period_start, target)
        model_counter = Counter()
        for row in top_rows:
            base = extract_base_model(row['text'])
            if base:
                model_counter[base] += 1
        top_5 = model_counter.most_common(5)
        top_labels = [item[0] for item in top_5]
        top_counts = [item[1] for item in top_5]

        sellers_all = await conn.fetch("SELECT id, name FROM sellers ORDER BY name")
        marked_ids = set()
        if target:
            marked = await conn.fetch("SELECT seller_id FROM seller_days WHERE date = $1", target)
            marked_ids = {r['seller_id'] for r in marked}
        sellers = [{"id": s['id'], "name": s['name'], "present": s['id'] in marked_ids} for s in sellers_all]

    sales_change_yesterday = None
    revenue_change_yesterday = None
    sales_change_week = None
    revenue_change_week = None
    if target == today:
        prev_stats = await get_previous_period_stats()
        if prev_stats['sales_yesterday']:
            sales_change_yesterday = round((sales_today - prev_stats['sales_yesterday']) / prev_stats['sales_yesterday'] * 100, 1)
        if prev_stats['revenue_yesterday']:
            revenue_change_yesterday = round((total_revenue - prev_stats['revenue_yesterday']) / prev_stats['revenue_yesterday'] * 100, 1)
        if prev_stats['sales_last_week']:
            avg_week = prev_stats['sales_last_week'] / 7
            if avg_week:
                sales_change_week = round((sales_today - avg_week) / avg_week * 100, 1)
        if prev_stats['revenue_last_week']:
            avg_rev_week = prev_stats['revenue_last_week'] / 7
            if avg_rev_week:
                revenue_change_week = round((total_revenue - avg_rev_week) / avg_rev_week * 100, 1)

    response = templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": {
            "date": target.strftime("%d.%m.%y"),
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
        "target_date": target.strftime("%d.%m.%y"),
        "target_date_iso": target.strftime("%Y-%m-%d"),
        "sales_today": sales_today,
        "revenue_today": total_revenue,
        "sales_change_yesterday": sales_change_yesterday,
        "revenue_change_yesterday": revenue_change_yesterday,
        "sales_change_week": sales_change_week,
        "revenue_change_week": revenue_change_week,
        "sellers": sellers,
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
    target_date: str
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
    target_date_str = data.target_date
    lock_key = f"dashboard:update_stats:{target_date_str}"

    if not await cache.lock(lock_key, ttl=30):
        return JSONResponse({"success": False, "error": "Обновление статистики уже выполняется"}, status_code=409)

    try:
        try:
            target_date = parse_date_any_format(data.target_date)
        except ValueError as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=400)

        pool = await get_pool()
        try:
            total_payments = data.cash + data.terminal + data.qr + data.transfer + data.invoice + data.installment
            if total_payments > 0 and data.sales_count == 0:
                data.sales_count = 1

            async with pool.acquire() as conn, conn.transaction():
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
    finally:
        await cache.unlock(lock_key)


@router.post("/toggle_seller_day")
async def toggle_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    target = parse_date_any_format(target_date)
    pool = await get_pool()
    async with pool.acquire() as conn:
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
