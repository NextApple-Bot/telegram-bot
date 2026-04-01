from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.repositories import StatsRepository
from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Получаем статистику за сегодня
    stats = await StatsRepository.get_today_stats()

    # Получаем финансовые итоги за сегодня
    pool = await get_pool()
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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "payments": payments,
        "total_revenue": total_revenue,
        "plan_amount": 600000  # можно взять из config
    })
