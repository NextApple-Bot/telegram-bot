# Файл: web_admin/routes/dashboard.py
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import date, timedelta
from collections import Counter
import re

from bot.repositories import StatsRepository
from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


def extract_base_model(full_text: str) -> str:
    """
    Извлекает базовую модель из текста товара:
    - Убирает цвет, память, серийные номера, комментарии в скобках.
    - Пример: "iPhone 16 Pro, Black, 128GB (SIM+eSIM)" -> "iPhone 16 Pro"
    """
    # Берём часть до первой запятой или открывающей скобки
    for sep in [',', '(', '（']:
        if sep in full_text:
            full_text = full_text.split(sep)[0]
            break
    # Удаляем числа с единицами памяти (128GB, 256GB, 1TB и т.д.)
    full_text = re.sub(r'\b\d+\s*(GB|TB|ГБ|ТБ)\b', '', full_text, flags=re.IGNORECASE)
    # Удаляем названия цветов
    colors = ['Black', 'White', 'Blue', 'Green', 'Yellow', 'Red', 'Purple', 'Pink',
              'Gold', 'Silver', 'Space Gray', 'Midnight', 'Starlight', 'Cream', 'Brown',
              'Rose Gold', 'Jet Black', 'Graphite', 'Sierra Blue', 'Alpine Green',
              'Deep Purple', 'Titanium', 'Desert', 'Natural', 'Sky Blue', 'Mist Blue',
              'Lavender', 'Sage', 'Cosmic Orange', 'Cloud White', 'Light Gold']
    for color in colors:
        full_text = re.sub(rf'\b{re.escape(color)}\b', '', full_text, flags=re.IGNORECASE)
    # Убираем лишние пробелы
    full_text = re.sub(r'\s+', ' ', full_text).strip()
    return full_text


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    days: int = Query(7, ge=7, le=90)
):
    # Статистика за сегодня
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

    # График продаж (линейный) за 7 дней
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

    # Топ-5 моделей за выбранный период
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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "payments": payments,
        "total_revenue": total_revenue,
        "plan_amount": 600000,
        "chart_dates": dates,
        "chart_sales": sales_counts,
        "top_labels": top_labels,
        "top_counts": top_counts,
        "days": days,
    })


# ---- API для динамической загрузки топ-моделей (без перезагрузки страницы) ----
@router.get("/top_models_data")
async def top_models_data(days: int = Query(7, ge=7, le=90)):
    """Возвращает JSON с топ-5 моделями за указанный период."""
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
    return JSONResponse(content={
        "labels": [item[0] for item in top_5],
        "counts": [item[1] for item in top_5]
    })
