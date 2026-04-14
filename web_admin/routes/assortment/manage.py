# Файл: web_admin/routes/assortment/manage.py
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List
import logging

from bot.services.assortment import AssortmentService
from bot.db import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


def validate_phone(phone: str) -> bool:
    if not phone:
        return True
    import re
    return bool(re.match(r'^\+7\d{10}$', phone))


@router.get("/edit/{item_id}")
async def edit_item_form(request: Request, item_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT i.id, i.text, i.serial, i.is_booked, i.created_at,
                   c.id as category_id, c.name as category_name,
                   i.booking_price, i.booking_prepayment, i.booking_platform,
                   i.booking_full_name, i.booking_phone, i.booking_payment_type,
                   i.sale_price, i.sale_prepayment, i.sale_payment_type,
                   i.sale_platform, i.sale_full_name, i.sale_phone, i.is_sold,
                   i.sale_payment_amount
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE i.id = $1
        """, item_id)
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        item = dict(row)
        categories = await conn.fetch("SELECT id, name FROM categories ORDER BY name")
    return templates.TemplateResponse("assortment_edit_item.html", {
        "request": request,
        "item": item,
        "categories": [dict(cat) for cat in categories],
    })


@router.post("/edit/{item_id}")
async def edit_item_submit(
    request: Request,
    item_id: int,
    text: str = Form(...),
    serial: Optional[str] = Form(None),
    category_id: int = Form(...),
    is_booked: bool = Form(False),
    is_sold: bool = Form(False),
    booking_price: Optional[float] = Form(None),
    booking_prepayment: Optional[float] = Form(None),
    booking_platform: Optional[str] = Form(None),
    booking_full_name: Optional[str] = Form(None),
    booking_phone: Optional[str] = Form(None),
    booking_payment_type: Optional[str] = Form(None),
    sale_price: Optional[float] = Form(None),
    sale_prepayment: Optional[float] = Form(None),
    sale_payment_amount: Optional[float] = Form(None),
    sale_payment_type: Optional[str] = Form(None),
    sale_platform: Optional[str] = Form(None),
    sale_full_name: Optional[str] = Form(None),
    sale_phone: Optional[str] = Form(None),
    accessory_name: List[str] = Form([]),
    accessory_serial: List[str] = Form([]),
    accessory_price: List[float] = Form([]),
    accessory_payment_type: List[str] = Form([]),
):
    logger.info(f"🟢 edit_item_submit ВЫЗВАН для item_id={item_id}, is_sold={is_sold}, is_booked={is_booked}")

    if booking_phone and not validate_phone(booking_phone):
        raise HTTPException(status_code=400, detail="Номер телефона брони должен быть в формате +7XXXXXXXXXX")
    if sale_phone and not validate_phone(sale_phone):
        raise HTTPException(status_code=400, detail="Номер телефона продажи должен быть в формате +7XXXXXXXXXX")

    pool = await get_pool()
    async with pool.acquire() as conn:
        old = await conn.fetchrow("SELECT is_sold, text, serial, category_id, is_booked FROM items WHERE id = $1", item_id)
        if not old:
            raise HTTPException(status_code=404, detail="Item not found")
        old_is_sold = old["is_sold"]
        old_text = old["text"]
        old_serial = old["serial"] or ""
        old_category_id = old["category_id"]
        old_is_booked = old["is_booked"]

        if old_is_sold:
            raise HTTPException(status_code=400, detail="Товар уже продан, редактирование невозможно")

        # Обработка ПРОДАЖИ
        if is_sold:
            accessories = []
            for name, acc_serial, price, pay_type in zip(
                accessory_name, accessory_serial, accessory_price, accessory_payment_type
            ):
                if name.strip() and price is not None and price > 0:
                    accessories.append({
                        "name": name.strip(),
                        "serial": acc_serial.strip() if acc_serial and acc_serial.strip() else None,
                        "price": price,
                        "payment_type": pay_type if pay_type else None
                    })

            from .sales import handle_sale_from_form
            await handle_sale_from_form(
                item_id=item_id, text=text, serial=serial, category_id=category_id,
                old_text=old_text, old_serial=old_serial, old_category_id=old_category_id,
                sale_price=sale_price, sale_prepayment=sale_prepayment,
                sale_payment_amount=sale_payment_amount, sale_payment_type=sale_payment_type,
                sale_platform=sale_platform, sale_full_name=sale_full_name, sale_phone=sale_phone,
                accessories=accessories
            )
            return RedirectResponse(url="/admin/assortment", status_code=303)

        # Обработка БРОНИ
        if is_booked:
            if not booking_price:
                raise HTTPException(status_code=400, detail="Укажите стоимость брони")
            await conn.execute("""
                UPDATE items
                SET text = $1, serial = $2, category_id = $3, is_booked = $4,
                    booking_price = $5, booking_prepayment = $6, booking_platform = $7,
                    booking_full_name = $8, booking_phone = $9, booking_payment_type = $10,
                    sale_price = NULL, sale_prepayment = NULL, sale_payment_type = NULL,
                    sale_platform = NULL, sale_full_name = NULL, sale_phone = NULL,
                    sale_payment_amount = NULL, is_sold = FALSE
                WHERE id = $11
            """, text, serial.strip().upper() if serial else None, category_id, is_booked,
               booking_price, booking_prepayment, booking_platform,
               booking_full_name, booking_phone, booking_payment_type, item_id)
            
            from .notifications import send_booking_notification
            await send_booking_notification(
                item_text=text,
                serial=serial.strip().upper() if serial else "без серийного номера",
                price=booking_price,
                prepayment=booking_prepayment,
                platform=booking_platform,
                full_name=booking_full_name,
                phone=booking_phone,
                payment_type=booking_payment_type,
                is_cancel=False
            )
            logger.info(f"Бронь товара {item_id} успешно сохранена")
        else:
            await conn.execute("""
                UPDATE items
                SET text = $1, serial = $2, category_id = $3, is_booked = $4,
                    booking_price = NULL, booking_prepayment = NULL, booking_platform = NULL,
                    booking_full_name = NULL, booking_phone = NULL, booking_payment_type = NULL,
                    sale_price = NULL, sale_prepayment = NULL, sale_payment_type = NULL,
                    sale_platform = NULL, sale_full_name = NULL, sale_phone = NULL,
                    sale_payment_amount = NULL, is_sold = FALSE
                WHERE id = $5
            """, text, serial.strip().upper() if serial else None, category_id, is_booked, item_id)
            
            if old_is_booked and not is_booked:
                from .notifications import send_booking_notification
                await send_booking_notification(
                    item_text=old_text,
                    serial=old_serial,
                    is_cancel=True
                )

    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/delete/{item_id}")
async def delete_item(request: Request, item_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT text, serial, category_id FROM items WHERE id = $1", item_id)
            if row:
                await conn.execute("""
                    INSERT INTO deleted_items (item_id, text, serial, category_id, reason)
                    VALUES ($1, $2, $3, $4, 'admin_manual')
                """, item_id, row["text"], row["serial"], row["category_id"])
                await conn.execute("DELETE FROM items WHERE id = $1", item_id)
    await AssortmentService.invalidate_cache()
    referer = request.headers.get("referer")
    if referer:
        return RedirectResponse(url=referer, status_code=303)
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/add")
async def add_item(
    request: Request,
    text: str = Form(...),
    serial: Optional[str] = Form(None),
    category_id: int = Form(...),
    is_booked: bool = Form(False),
    booking_price: Optional[float] = Form(None),
    booking_prepayment: Optional[float] = Form(None),
    booking_platform: Optional[str] = Form(None),
    booking_full_name: Optional[str] = Form(None),
    booking_phone: Optional[str] = Form(None),
    booking_payment_type: Optional[str] = Form(None),
):
    if booking_phone and not validate_phone(booking_phone):
        raise HTTPException(status_code=400, detail="Номер телефона брони должен быть в формате +7XXXXXXXXXX")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO items (text, serial, category_id, is_booked,
                               booking_price, booking_prepayment, booking_platform,
                               booking_full_name, booking_phone, booking_payment_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, text, serial.strip().upper() if serial else None, category_id, is_booked,
           booking_price, booking_prepayment, booking_platform,
           booking_full_name, booking_phone, booking_payment_type)
        if is_booked:
            from .notifications import send_booking_notification
            await send_booking_notification(
                item_text=text,
                serial=serial.strip().upper() if serial else "без серийного номера",
                price=booking_price,
                prepayment=booking_prepayment,
                platform=booking_platform,
                full_name=booking_full_name,
                phone=booking_phone,
                payment_type=booking_payment_type,
                is_cancel=False
            )
    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/add_category")
async def add_category(request: Request, name: str = Form(...)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO categories (name) VALUES ($1)", name)
    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)
