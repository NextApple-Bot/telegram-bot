# Файл: web_admin/routes/dashboard.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta
from collections import Counter
import re
import logging

from bot.repositories import StatsRepository
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


async def get_previous_period_stats():
    """Возвращает продажи и выручку за вчера и за прошлую неделю."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week_start = today - timedelta(days=7)
    last_week_end = today - timedelta(days=1)
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Продажи за вчера
        sales_yesterday = await conn.fetchval('SELECT COUNT(*) FROM sales WHERE DATE(sold_at) = $1', yesterday)
        # Выручка за вчера
        revenue_yesterday_rows = await conn.fetch('''
            SELECT COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as total
            FROM sales WHERE DATE(sold_at) = $1
        ''', yesterday)
        revenue_yesterday = revenue_yesterday_rows[0]['total'] if revenue_yesterday_rows else 0
        # Продажи за прошлую неделю (7 дней)
        sales_last_week = await conn.fetchval('SELECT COUNT(*) FROM sales WHERE sold_at >= $1 AND sold_at < $2', last_week_start, today)
        # Выручка за прошлую неделю
        revenue_last_week_rows = await conn.fetch('''
            SELECT COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                   COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as total
            FROM sales WHERE sold_at >= $1 AND sold_at < $2
        ''', last_week_start, today)
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
    days: int = Query(7, ge=7, le=90)
):
    # Пытаемся получить кэшированные данные дашборда на сегодня
    cache_key = f"dashboard:summary:{date.today().isoformat()}"
    cached_data = await cache.get(cache_key)
    
    if cached_data:
        stats = cached_data.get('stats')
        payments = cached_data.get('payments')
        total_revenue = cached_data.get('total_revenue')
        sales_counts = cached_data.get('sales_counts')
        revenue_counts = cached_data.get('revenue_counts')
        dates = cached_data.get('dates')
        top_labels = cached_data.get('top_labels')
        top_counts = cached_data.get('top_counts')
        prev_stats = await get_previous_period_stats()
        sales_today = stats['sales_count']
        revenue_today = total_revenue
        
        sales_change_yesterday = 0
        if prev_stats['sales_yesterday']:
            sales_change_yesterday = (sales_today - prev_stats['sales_yesterday']) / prev_stats['sales_yesterday'] * 100
        revenue_change_yesterday = 0
        if prev_stats['revenue_yesterday']:
            revenue_change_yesterday = (revenue_today - prev_stats['revenue_yesterday']) / prev_stats['revenue_yesterday'] * 100
        sales_change_week = 0
        if prev_stats['sales_last_week']:
            sales_change_week = (sales_today - prev_stats['sales_last_week'] / 7) / (prev_stats['sales_last_week'] / 7) * 100
        revenue_change_week = 0
        if prev_stats['revenue_last_week']:
            revenue_change_week = (revenue_today - prev_stats['revenue_last_week'] / 7) / (prev_stats['revenue_last_week'] / 7) * 100
    else:
        stats = await StatsRepository.get_today_stats()
        pool = await get_pool()

        # Финансы за сегодня
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT payment_type, SUM(amount) as total
                FROM daily_payments
                WHERE DATE(created_at) = CURRENT_DATE
                GROUP BY payment_type
            ''')
        payments = {row['payment_type']: float(row['total']) for row in rows}
        for pt in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']:
            payments.setdefault(pt, 0.0)
        total_revenue = sum(payments.values())

        # График продаж (количество) за 7 дней
        end_date = date.today()
        start_date = end_date - timedelta(days=6)
        async with pool.acquire() as conn:
            sales_rows = await conn.fetch('''
                SELECT DATE(sold_at) as day, COUNT(*) as count
                FROM sales
                WHERE sold_at >= $1
                GROUP BY day
                ORDER BY day
            ''', start_date)
        sales_dict = {row['day'].isoformat(): row['count'] for row in sales_rows}
        dates = [(start_date + timedelta(days=i)).isoformat() for i in range(7)]
        sales_counts = [sales_dict.get(d, 0) for d in dates]

        # График выручки (деньги) за 7 дней
        async with pool.acquire() as conn:
            revenue_rows = await conn.fetch('''
                SELECT DATE(sold_at) as day,
                       COALESCE(SUM(cash),0) + COALESCE(SUM(terminal),0) + COALESCE(SUM(qr),0) +
                       COALESCE(SUM(transfer),0) + COALESCE(SUM(invoice),0) + COALESCE(SUM(installment),0) as revenue
                FROM sales
                WHERE sold_at >= $1
                GROUP BY day
                ORDER BY day
            ''', start_date)
        revenue_dict = {row['day'].isoformat(): float(row['revenue']) for row in revenue_rows}
        revenue_counts = [revenue_dict.get(d, 0) for d in dates]

        # Топ-5 моделей (кэш)
        top_cache_key = f"dashboard:top_models:{days}"
        cached_top = await cache.get(top_cache_key)
        if cached_top:
            top_labels, top_counts = cached_top
        else:
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
            top_labels = [item[0] for item in top_5]
            top_counts = [item[1] for item in top_5]
            await cache.set(top_cache_key, (top_labels, top_counts), ttl=3600)

        # Динамика по сравнению с предыдущим периодом
        prev_stats = await get_previous_period_stats()
        sales_today = stats['sales_count']
        revenue_today = total_revenue

        sales_change_yesterday = 0
        if prev_stats['sales_yesterday']:
            sales_change_yesterday = (sales_today - prev_stats['sales_yesterday']) / prev_stats['sales_yesterday'] * 100
        revenue_change_yesterday = 0
        if prev_stats['revenue_yesterday']:
            revenue_change_yesterday = (revenue_today - prev_stats['revenue_yesterday']) / prev_stats['revenue_yesterday'] * 100

        sales_change_week = 0
        if prev_stats['sales_last_week']:
            sales_change_week = (sales_today - prev_stats['sales_last_week'] / 7) / (prev_stats['sales_last_week'] / 7) * 100
        revenue_change_week = 0
        if prev_stats['revenue_last_week']:
            revenue_change_week = (revenue_today - prev_stats['revenue_last_week'] / 7) / (prev_stats['revenue_last_week'] / 7) * 100

        # Сохраняем кэш дашборда (кроме top_models, у которых свой TTL)
        cache_payload = {
            'stats': stats,
            'payments': payments,
            'total_revenue': total_revenue,
            'sales_counts': sales_counts,
            'revenue_counts': revenue_counts,
            'dates': dates,
            'top_labels': top_labels,
            'top_counts': top_counts,
        }
        await cache.set(cache_key, cache_payload, ttl=60)  # 1 минута

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "payments": payments,
        "total_revenue": total_revenue,
        "plan_amount": 600000,
        "chart_dates": dates,
        "chart_sales": sales_counts,
        "chart_revenue": revenue_counts,
        "top_labels": top_labels,
        "top_counts": top_counts,
        "days": days,
        "sales_today": sales_today,
        "revenue_today": revenue_today,
        "sales_change_yesterday": round(sales_change_yesterday, 1),
        "revenue_change_yesterday": round(revenue_change_yesterday, 1),
        "sales_change_week": round(sales_change_week, 1),
        "revenue_change_week": round(revenue_change_week, 1),
    })


@router.get("/top_models_data")
async def top_models_data(days: int = Query(7, ge=7, le=90)):
    cache_key = f"dashboard:top_models:{days}"
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
    await cache.set(cache_key, (labels, counts), ttl=3600)
    return JSONResponse(content={"labels": labels, "counts": counts})
