# Файл: web_admin/routes/dashboard.py
from datetime import datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

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

        # Продавцы и отметки присутствия
        sellers_rows = await conn.fetch("""
            SELECT s.id, s.name,
                   (sd.seller_id IS NOT NULL) as present
            FROM sellers s
            LEFT JOIN seller_days sd ON s.id = sd.seller_id AND sd.date = $1
            ORDER BY s.name
        """, today)
        sellers = [dict(r) for r in sellers_rows]

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
    target_date: str = Form(...),
):
    """Добавляет или удаляет отметку о присутствии продавца в указанный день."""
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return {"success": False, "error": "Неверный формат даты"}

    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM seller_days WHERE seller_id = $1 AND date = $2",
            seller_id, date_obj
        )
        if existing:
            await conn.execute("DELETE FROM seller_days WHERE id = $1", existing["id"])
            status = "removed"
        else:
            try:
                await conn.execute(
                    "INSERT INTO seller_days (seller_id, date) VALUES ($1, $2)",
                    seller_id, date_obj
                )
                status = "added"
            except Exception:
                status = "exists"
    return {"success": True, "status": status}


@router.post("/update_stats")
async def update_stats(request: Request):
    """Сохраняет отредактированные данные статистики за день."""
    data = await request.json()
    target_date_str = data.get("target_date")
    if not target_date_str:
        return JSONResponse({"success": False, "error": "target_date is required"}, status_code=400)

    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверный формат даты"}, status_code=400)

    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Обновление платежей
        await conn.execute("DELETE FROM daily_payments WHERE DATE(created_at) = $1", target_date)
        payment_types = ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']
        for pt in payment_types:
            amount = float(data.get(pt, 0))
            if amount > 0:
                await conn.execute(
                    "INSERT INTO daily_payments (type, payment_type, amount, created_at) VALUES ('sale', $1, $2, $3)",
                    pt, amount, target_date
                )

        # Обновление количества продаж
        sales_count = int(data.get("sales_count", 0))
        await conn.execute("DELETE FROM sales WHERE DATE(sold_at) = $1", target_date)
        for _ in range(sales_count):
            await conn.execute("INSERT INTO sales (sold_at) VALUES ($1)", target_date)

        # Обновление количества предзаказов
        preorders_count = int(data.get("preorders_count", 0))
        await conn.execute("DELETE FROM preorders WHERE DATE(created_at) = $1", target_date)
        for _ in range(preorders_count):
            await conn.execute("INSERT INTO preorders (created_at) VALUES ($1)", target_date)

        # Обновление количества броней
        bookings_count = int(data.get("bookings_count", 0))
        await conn.execute("DELETE FROM bookings WHERE DATE(booked_at) = $1", target_date)
        for _ in range(bookings_count):
            # ИСПРАВЛЕНО: используем item_id=0 (служебный товар)
            await conn.execute("INSERT INTO bookings (item_id, booked_at) VALUES (0, $1)", target_date)

    return JSONResponse({"success": True})


@router.get("/top_models_data")
async def top_models_data(request: Request, days: int = 7, target_date: str | None = None):
    """Возвращает данные для графика топ-5 моделей (заглушка)."""
    # В реальной реализации нужно считать проданные товары за период,
    # здесь возвращаем пустые списки, чтобы график не ломался.
    return JSONResponse({"labels": [], "counts": []})
