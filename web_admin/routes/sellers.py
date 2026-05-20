from fastapi import APIRouter, Form, Query, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from datetime import date, timedelta, datetime
from typing import Optional
import logging

from bot.db import get_async_session_factory
from bot.models import Seller, SellerDay, Sale
from sqlalchemy import select, func
from web_admin.templates import templates

router = APIRouter()
logger = logging.getLogger(__name__)


def parse_date_any_format(date_str: str) -> date:
    for fmt in ["%Y-%m-%d", "%d.%m.%y"]:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {date_str}")


@router.get("/manage")
async def seller_manage(request: Request):
    async_session = get_async_session_factory()
    async with async_session() as session:
        sellers = (await session.execute(select(Seller).order_by(Seller.name))).scalars().all()
    return templates.TemplateResponse("sellers_manage.html", {"request": request, "sellers": sellers})


@router.post("/add")
async def add_seller(request: Request, name: str = Form(...)):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Имя продавца не может быть пустым")
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        exists = await session.execute(select(Seller).where(Seller.name == name))
        if exists.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Продавец с таким именем уже существует")
        session.add(Seller(name=name))
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.post("/delete/{seller_id}")
async def delete_seller(seller_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        seller = await session.get(Seller, seller_id)
        if seller:
            await session.delete(seller)
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.post("/mark_day")
async def mark_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    target = parse_date_any_format(target_date)
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        await session.execute(
            "INSERT INTO seller_days (seller_id, date) VALUES (:sid, :d) ON CONFLICT DO NOTHING",
            {"sid": seller_id, "d": target}
        )
    return RedirectResponse(url=f"/admin/dashboard?target_date={target_date}", status_code=303)


@router.post("/unmark_day")
async def unmark_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    target = parse_date_any_format(target_date)
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        await session.execute(
            "DELETE FROM seller_days WHERE seller_id = :sid AND date = :d",
            {"sid": seller_id, "d": target}
        )
    return RedirectResponse(url=f"/admin/dashboard?target_date={target_date}", status_code=303)


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

    async_session = get_async_session_factory()
    async with async_session() as session:
        sellers = (await session.execute(select(Seller).order_by(Seller.name))).scalars().all()
        results = []
        for s in sellers:
            days_worked = await session.execute(
                select(func.count(SellerDay.id)).where(
                    SellerDay.seller_id == s.id,
                    SellerDay.date.between(start_date, end_date)
                )
            )
            days_worked = days_worked.scalar() or 0

            if days_worked == 0:
                total_count = 0
                total_revenue = 0.0
            else:
                total_count = 0
                total_revenue = 0.0
                current = start_date
                while current <= end_date:
                    worked = await session.execute(
                        select(SellerDay.id).where(SellerDay.seller_id == s.id, SellerDay.date == current)
                    )
                    if worked.scalar():
                        cnt_sellers = await session.execute(
                            select(func.count(SellerDay.id)).where(SellerDay.date == current)
                        )
                        cnt_sellers = cnt_sellers.scalar() or 1

                        day_sales = await session.execute(
                            select(
                                func.coalesce(func.sum(Sale.count), 0),
                                func.coalesce(func.sum(Sale.cash + Sale.terminal + Sale.qr + Sale.transfer + Sale.invoice + Sale.installment), 0)
                            ).where(func.date(Sale.sold_at) == current)
                        )
                        row = day_sales.first()
                        if row:
                            total_count += row[0] / cnt_sellers
                            total_revenue += float(row[1]) / cnt_sellers
                    current += timedelta(days=1)

            results.append({
                "id": s.id,
                "name": s.name,
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
