# Файл: web_admin/routes/dashboard.py
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request

from bot.db import get_pool
from web_admin.main import templates

router = APIRouter()


@router.get("/")
async def dashboard(request: Request, target_date: str | None = None):
    today = datetime.now().date() if not target_date else datetime.strptime(target_date, "%Y-%m-%d").date()

    pool = await get_pool()
    async with pool.acquire() as conn:
        # продажи за день
        sales = await conn.fetchval("SELECT COUNT(*) FROM sales WHERE DATE(sold_at) = $1", today) or 0
        # выручка
        row = await conn.fetchrow("""
            SELECT COALESCE(SUM(cash),0) as cash, COALESCE(SUM(terminal),0) as terminal,
                   COALESCE(SUM(qr),0) as qr, COALESCE(SUM(transfer),0) as transfer,
                   COALESCE(SUM(invoice),0) as invoice, COALESCE(SUM(installment),0) as installment
            FROM daily_payments WHERE DATE(created_at) = $1
        """, today)
        payments = dict(row) if row else {}
        total_revenue = sum(payments.values())
        plan = 600000  # можно взять из config

        # прочая статистика
        stats = await conn.fetchrow("""
            SELECT (SELECT COUNT(*) FROM preorders WHERE DATE(created_at)=$1) as preorders_count,
                   (SELECT COUNT(*) FROM bookings WHERE DATE(booked_at)=$1) as bookings_count
        """, today)
        preorders_count = stats["preorders_count"] if stats else 0
        bookings_count = stats["bookings_count"] if stats else 0

        # графики
        dates = [(today - timedelta(days=i)).strftime("%d.%m") for i in range(6, -1, -1)]
        sales_chart = []
        revenue_chart = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            cnt = await conn.fetchval("SELECT COUNT(*) FROM sales WHERE DATE(sold_at)=$1", d) or 0
            rev_row = await conn.fetchrow("SELECT COALESCE(SUM(amount),0) FROM daily_payments WHERE DATE(created_at)=$1", d)
            sales_chart.append(cnt)
            revenue_chart.append(float(rev_row[0]) if rev_row else 0)

        # продавцы
        sellers_rows = await conn.fetch("SELECT id, name FROM sellers ORDER BY name")
        sellers = [dict(r) for r in sellers_rows]
        # топ-модели (заглушка)
        top_labels = []
        top_counts = []

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "target_date": today.strftime("%d.%m.%Y"),
        "target_date_iso": today.isoformat(),
        "sales_today": sales,
        "revenue_today": total_revenue,
        "sales_change_yesterday": 0,
        "sales_change_week": 0,
        "revenue_change_yesterday": 0,
        "revenue_change_week": 0,
        "payments": payments,
        "total_revenue": total_revenue,
        "plan_amount": plan,
        "stats": {"sales_count": sales, "preorders_count": preorders_count, "bookings_count": bookings_count},
        "sellers": sellers,
        "chart_dates": dates,
        "chart_sales": sales_chart,
        "chart_revenue": revenue_chart,
        "top_labels": top_labels,
        "top_counts": top_counts,
        "days": 7,
    })
