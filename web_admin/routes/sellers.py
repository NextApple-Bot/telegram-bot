# Файл: web_admin/routes/sellers.py
from fastapi import APIRouter, Request, Query, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, date, timedelta
from typing import Optional, List
import logging

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
    for fmt in ["%Y-%m-%d", "%d.%m.%y"]:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {date_str}")


# --- CRUD ---
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
        # Проверяем существование
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


# --- Отметка рабочих дней (используется с дашборда) ---
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
        except Exception as e:
            raise HTTPException(status_code=400, detail="Ошибка отметки дня")
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


# --- Статистика ---
@router.get("/stats", response_class=HTMLResponse)
async def sellers_stats(
    request: Request,
    target_date: Optional[str] = Query(None),
    mode: str = Query("preset", regex="^(preset|month|range)$"),
    days: int = Query(7, ge=7, le=90),
    month: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    # ... (код статистики без изменений) ...
