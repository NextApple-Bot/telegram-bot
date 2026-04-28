# Файл: web_admin/routes/sellers.py
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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


@router.get("/manage", response_class=HTMLResponse)
async def manage_sellers(request: Request):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name FROM sellers ORDER BY name")
        sellers = [dict(r) for r in rows]
    return templates.TemplateResponse("sellers_manage.html", {
        "request": request,
        "sellers": sellers,
    })


@router.post("/add")
async def add_seller(name: str = Form(...)):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Имя продавца не может быть пустым")
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM sellers WHERE name = $1", name)
        if exists:
            raise HTTPException(status_code=400, detail="Продавец с таким именем уже существует")
        await conn.execute("INSERT INTO sellers (name) VALUES ($1)", name)
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.post("/delete/{seller_id}")
async def delete_seller(seller_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sellers WHERE id = $1", seller_id)
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.post("/mark_day")
async def mark_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    target = parse_date_any_format(target_date)
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO seller_days (seller_id, date) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                seller_id, target
            )
        except Exception as err:
            raise HTTPException(status_code=400, detail="Ошибка отметки дня") from err
    return RedirectResponse(url=f"/admin/dashboard?target_date={target_date}", status_code=303)


@router.post("/unmark_day")
async def unmark_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    target = parse_date_any_format(target_date)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM seller_days WHERE seller_id = $1 AND date = $2",
            seller_id, target
        )
    return RedirectResponse(url=f"/admin/dashboard?target_date={target_date}", status_code=303)


@router.get("/stats", response_class=HTMLResponse)
async def sellers_stats(
    request: Request,
    target_date: str | None = Query(None),
    mode: str = Query("preset", regex="^(preset|month|range)$"),
    days: int = Query(7, ge=7, le=90),
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
        sellers = await conn.fetch("SELECT id, name FROM sellers ORDER BY name")
        sellers = [dict(s) for s in sellers]

        results = []
        for s in sellers:
            days_worked = await conn.fetchval(
                "SELECT COUNT(*) FROM seller_days WHERE seller_id = $1 AND date BETWEEN $2 AND $3",
                s['id'], start_date, end_date
            )
            if days_worked == 0:
                total_count = 0
                total_revenue = 0.0
            else:
                total_count = 0
                total_revenue = 0.0
                current = start_date
                while current <= end_date:
                    worked = await conn.fetchval(
                        "SELECT 1 FROM seller_days WHERE seller_id = $1 AND date = $2",
                        s['id'], current
                    )
                    if worked:
                        cnt_sellers = await conn.fetchval(
                            "SELECT COUNT(*) FROM seller_days WHERE date = $1", current
                        )
                        day_sales = await conn.fetchrow(
                            "SELECT COALESCE(SUM(count),0) as cnt, "
                            "COALESCE(SUM(cash),0)+COALESCE(SUM(terminal),0)+COALESCE(SUM(qr),0)+"
                            "COALESCE(SUM(transfer),0)+COALESCE(SUM(invoice),0)+COALESCE(SUM(installment),0) as rev "
                            "FROM sales WHERE DATE(sold_at) = $1",
                            current
                        )
                        if day_sales and cnt_sellers > 0:
                            total_count += int(day_sales['cnt']) / cnt_sellers
                            total_revenue += float(day_sales['rev']) / cnt_sellers
                    current += timedelta(days=1)

            results.append({
                "id": s['id'],
                "name": s['name'],
                "days_worked": days_worked,
                "total_count": round(total_count, 1),
                "total_revenue": round(total_revenue, 2),
            })

    return templates.TemplateResponse("sellers_stats.html", {
        "request": request,
        "mode": mode,
        "days": days,
        "target_date": end_date.strftime("%Y-%m-%d") if mode == "preset" else "",
        "month": f"{start_date.year}-{start_date.month:02d}" if mode == "month" else "",
        "date_from": start_date.strftime("%Y-%m-%d") if mode == "range" else "",
        "date_to": end_date.strftime("%Y-%m-%d") if mode == "range" else "",
        "results": results,
    })
