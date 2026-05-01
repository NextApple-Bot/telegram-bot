# Файл: web_admin/routes/dashboard.py
from datetime import datetime, timedelta

from fastapi import APIRouter, Form, Request

from bot.db import get_pool
from web_admin.templates import templates

router = APIRouter()


@router.get("/")
async def dashboard(request: Request, target_date: str | None = None):
    today = datetime.now().date() if not target_date else datetime.strptime(target_date, "%Y-%m-%d").date()

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Количество продаж за выбранную дату
        sales = await conn.fetchval("SELECT COUNT(*) FROM sales WHERE DATE(sold_at) = $1", today) or 0

        # Суммы платежей по типам из daily_payments
        row = await conn.fetchrow("""
            SELECT 
                COALESCE(SUM(amount) FILTER (WHERE payment_type = 'cash'), 0) as cash,
                COALESCE(SUM(amount) FILTER (WHERE payment_type = 'terminal'), 0) as terminal,
                COALESCE(SUM(amount) FILTER (WHERE payment_type = 'qr'), 0) as qr,
                COALESCE(SUM(amount) FILTER (WHERE payment_type = 'transfer'), 0) as transfer,
                COALESCE(SUM(amount) FILTER (WHERE payment_type = 'invoice'), 0) as invoice,
                COALESCE(SUM(amount) FILTER (WHERE payment_type = 'installment'), 0) as installment
            FROM daily_payments WHERE DATE(created_at) = $1
        """, today)

        payments = dict(row) if row else {}
        total_revenue = sum(payments.values())
        plan = 600000

        # Количество предзаказов и броней за дату
        stats = await conn.fetchrow("""
            SELECT 
                (SELECT COUNT(*) FROM preorders WHERE DATE(created_at)=$1) as preorders_count,
                (SELECT COUNT(*) FROM bookings WHERE DATE(booked_at)=$1) as bookings_count
        """, today)
        preorders_count = stats["preorders_count"] if stats else 0
        bookings_count = stats["bookings_count"] if stats else 0

        # Графики за последние 7 дней
        dates = [(today - timedelta(days=i)).strftime("%d.%m") for i in range(6, -1, -1)]
        sales_chart = []
        revenue_chart = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            cnt = await conn.fetchval("SELECT COUNT(*) FROM sales WHERE DATE(sold_at)=$1", d) or 0
            rev_row = await conn.fetchrow("""
                SELECT COALESCE(SUM(amount), 0) FROM daily_payments WHERE DATE(created_at)=$1
            """, d)
            sales_chart.append(cnt)
            revenue_chart.append(float(rev_row[0]) if rev_row else 0)

        # Список продавцов и отметки присутствия на выбранную дату
        sellers_rows = await conn.fetch("""
            SELECT s.id, s.name, 
                   (sd.seller_id IS NOT NULL) as present
            FROM sellers s
            LEFT JOIN seller_days sd ON s.id = sd.seller_id AND sd.date = $1
            ORDER BY s.name
        """, today)
        sellers = [dict(r) for r in sellers_rows]

        # Топ-5 моделей (заглушка)
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


@router.post("/toggle_seller_day")
async def toggle_seller_day(
    request: Request,
    seller_id: int = Form(...),
    target_date: str = Form(...),  # в формате YYYY-MM-DD
):
    """Добавляет или удаляет отметку о присутствии продавца в указанный день."""
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return {"success": False, "error": "Неверный формат даты"}

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Проверяем, существует ли запись
        existing = await conn.fetchrow(
            "SELECT id FROM seller_days WHERE seller_id = $1 AND date = $2",
            seller_id, date_obj
        )
        if existing:
            # Удаляем – это переключение в состояние "отсутствует"
            await conn.execute("DELETE FROM seller_days WHERE id = $1", existing["id"])
            status = "removed"
        else:
            # Добавляем
            try:
                await conn.execute(
                    "INSERT INTO seller_days (seller_id, date) VALUES ($1, $2)",
                    seller_id, date_obj
                )
                status = "added"
            except Exception:
                # Возможно, уже существует (гонка), тогда считаем успехом
                status = "exists"

    return {"success": True, "status": status}
