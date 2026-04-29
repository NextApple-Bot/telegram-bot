# Файл: web_admin/routes/sellers.py
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse

from bot.db import get_pool
from web_admin.templates import templates

router = APIRouter()


@router.get("/manage")
async def seller_manage(request: Request):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM sellers ORDER BY name")
        sellers = [dict(r) for r in rows]
    return templates.TemplateResponse("sellers_manage.html", {"request": request, "sellers": sellers})


@router.post("/add")
async def add_seller(request: Request, name: str = Form(...)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO sellers (name) VALUES ($1) ON CONFLICT DO NOTHING", name)
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.post("/delete/{seller_id}")
async def delete_seller(seller_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sellers WHERE id = $1", seller_id)
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.get("/stats")
async def seller_stats(
    request: Request,
    target_date: str | None = None,
    days: int = Query(7, ge=1, le=365),
    mode: str = Query("preset"),
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    return templates.TemplateResponse("sellers_stats.html", {
        "request": request,
        "mode": mode,
        "target_date": target_date or "",
        "days": days,
        "results": [],
    })
