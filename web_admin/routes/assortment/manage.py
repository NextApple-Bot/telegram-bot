import asyncio
import logging

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import Category, DeletedItem, Item
from bot.repositories.client import ClientRepository
from bot.services.assortment import AssortmentService
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


def validate_phone(phone: str) -> bool:
    if not phone:
        return True
    import re
    return bool(re.match(r'^\+7\d{10}$', phone))


@router.get("/edit/{item_id}")
async def edit_item_form(request: Request, item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        item = await session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        categories = await session.execute(select(Category).order_by(Category.sort_order, Category.name))
        categories = list(categories.scalars().all())
    return templates.TemplateResponse("assortment_edit_item.html", {
        "request": request,
        "item": item,
        "categories": [{"id": c.id, "name": c.name} for c in categories],
    })


@router.post("/edit/{item_id}")
async def edit_item_submit(
    request: Request,
    item_id: int,
    text: str = Form(...),
    serial: str | None = Form(None),
    category_id: int = Form(...),
    is_booked: bool = Form(False),
    is_sold: bool = Form(False),
    booking_price: float | None = Form(None),
    booking_bonus: float | None = Form(None),
    booking_bonus_reason: str | None = Form(None),
    booking_prepayment: float | None = Form(None),
    booking_platform: str | None = Form(None),
    booking_full_name: str | None = Form(None),
    booking_phone: str | None = Form(None),
    booking_payment_type: str | None = Form(None),
    booking_birth_date: str | None = Form(None),
    sale_price: float | None = Form(None),
    sale_bonus: float | None = Form(None),
    sale_bonus_reason: str | None = Form(None),
    sale_change: float | None = Form(None),
    sale_change_type: str | None = Form(None),
    sale_prepayment: float | None = Form(None),
    sale_payment_amount: float | None = Form(None),
    sale_payment_type: str | None = Form(None),
    sale_platform: str | None = Form(None),
    sale_full_name: str | None = Form(None),
    sale_phone: str | None = Form(None),
    sale_birth_date: str | None = Form(None),
    accessory_name: list[str] = Form([]),
    accessory_serial: list[str] = Form([]),
    accessory_price: list[float] = Form([]),
    accessory_payment_type: list[str] = Form([]),
):
    logger.info(f"edit_item_submit {item_id} is_sold={is_sold} is_booked={is_booked}")

    if booking_phone and not validate_phone(booking_phone):
        raise HTTPException(status_code=400, detail="Номер телефона брони должен быть в формате +7XXXXXXXXXX")
    if sale_phone and not validate_phone(sale_phone):
        raise HTTPException(status_code=400, detail="Номер телефона продажи должен быть в формате +7XXXXXXXXXX")

    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
                old = await session.get(Item, item_id, populate_existing=True, with_for_update=True)
                if not old:
                    raise HTTPException(status_code=404, detail="Item not found")
                old_is_sold = old.is_sold
                old_text = old.text
                old_serial = old.serial or ""
                old_category_id = old.category_id
                old_is_booked = old.is_booked

                if old_is_sold:
                    raise HTTPException(status_code=400, detail="Товар уже продан, редактирование невозможно")

                if is_sold and is_booked:
                    raise HTTPException(status_code=400, detail="Снимите бронь перед продажей")

                notify_booking = None
                notify_cancel = None

                if is_sold:
                    accessories = []
                    for name, acc_serial, price, pay_type in zip(
                        accessory_name, accessory_serial, accessory_price, accessory_payment_type, strict=False
                    ):
                        if name.strip() and price is not None and price > 0:
                            accessories.append({
                                "name": name.strip(),
                                "serial": acc_serial.strip() if acc_serial and acc_serial.strip() else None,
                                "price": price,
                                "payment_type": pay_type if pay_type else None
                            })

                    from .sales import handle_sale_from_form
                    result = await handle_sale_from_form(
                        item_id=item_id, text=text, serial=serial, category_id=category_id,
                        old_text=old_text, old_serial=old_serial, old_category_id=old_category_id,
                        sale_price=sale_price, sale_prepayment=sale_prepayment,
                        sale_payment_amount=sale_payment_amount, sale_payment_type=sale_payment_type,
                        sale_platform=sale_platform, sale_full_name=sale_full_name, sale_phone=sale_phone,
                        sale_birth_date=sale_birth_date,
                        sale_bonus=sale_bonus, sale_bonus_reason=sale_bonus_reason,
                        sale_change=sale_change, sale_change_type=sale_change_type,
                        accessories=accessories,
                        conn=session
                    )
                    if "error" in result:
                        raise HTTPException(status_code=400, detail=result["error"])
                    await AssortmentService.invalidate_cache()
                    return RedirectResponse(url="/admin/assortment", status_code=303)

                if is_booked:
                    if not booking_price:
                        raise HTTPException(status_code=400, detail="Укажите стоимость брони")

                    if booking_phone or booking_full_name:
                        await ClientRepository.get_or_create_client(
                            phone=booking_phone,
                            full_name=booking_full_name,
                            social_network=booking_platform,
                            birth_date=booking_birth_date,
                            conn=session
                        )

                    old.text = text
                    old.serial = serial.strip().upper() if serial else None
                    old.category_id = category_id
                    old.is_booked = True
                    old.booking_price = booking_price
                    old.booking_bonus = booking_bonus
                    old.booking_bonus_reason = booking_bonus_reason
                    old.booking_prepayment = booking_prepayment
                    old.booking_platform = booking_platform
                    old.booking_full_name = booking_full_name
                    old.booking_phone = booking_phone
                    old.booking_payment_type = booking_payment_type
                    old.sale_price = None
                    old.sale_bonus = None
                    old.sale_bonus_reason = None
                    old.sale_change = None
                    old.sale_change_type = None
                    old.sale_prepayment = None
                    old.sale_payment_type = None
                    old.sale_platform = None
                    old.sale_full_name = None
                    old.sale_phone = None
                    old.sale_payment_amount = None
                    old.is_sold = False
                    session.add(old)

                    if booking_prepayment and booking_prepayment > 0 and booking_payment_type:
                        from bot.models import DailyPayment
                        payment = DailyPayment(
                            type='preorder',
                            payment_type=booking_payment_type,
                            amount=booking_prepayment
                        )
                        session.add(payment)

                    notify_booking = {
                        "item_text": text,
                        "serial": serial.strip().upper() if serial else "без серийного номера",
                        "price": booking_price,
                        "bonus": booking_bonus,
                        "bonus_reason": booking_bonus_reason,
                        "prepayment": booking_prepayment,
                        "platform": booking_platform,
                        "full_name": booking_full_name,
                        "phone": booking_phone,
                        "payment_type": booking_payment_type,
                        "birth_date": booking_birth_date,
                        "is_cancel": False
                    }
                else:
                    old.text = text
                    old.serial = serial.strip().upper() if serial else None
                    old.category_id = category_id
                    old.is_booked = False
                    old.booking_price = None
                    old.booking_bonus = None
                    old.booking_bonus_reason = None
                    old.booking_prepayment = None
                    old.booking_platform = None
                    old.booking_full_name = None
                    old.booking_phone = None
                    old.booking_payment_type = None
                    old.sale_price = None
                    old.sale_bonus = None
                    old.sale_bonus_reason = None
                    old.sale_change = None
                    old.sale_change_type = None
                    old.sale_prepayment = None
                    old.sale_payment_type = None
                    old.sale_platform = None
                    old.sale_full_name = None
                    old.sale_phone = None
                    old.sale_payment_amount = None
                    old.is_sold = False
                    session.add(old)

                    if old_is_booked and not is_booked:
                        notify_cancel = {
                            "item_text": old_text,
                            "serial": old_serial,
                            "is_cancel": True
                        }

            # Уведомления после коммита
            if notify_booking:
                from .notifications import send_booking_notification
                asyncio.create_task(send_booking_notification(**notify_booking))
                logger.info(f"Бронь товара {item_id} сохранена, уведомление отправлено")
            if notify_cancel:
                from .notifications import send_booking_notification
                asyncio.create_task(send_booking_notification(**notify_cancel))

        except HTTPException:
            raise
        except SQLAlchemyError as e:
            logger.exception(f"Ошибка БД при редактировании товара {item_id}: {e}")
            raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера") from e

    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/delete/{item_id}")
async def delete_item(request: Request, item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        item = await session.get(Item, item_id)
        if item:
            deleted = DeletedItem(
                item_id=item.id,
                text=item.text,
                serial=item.serial,
                category_id=item.category_id,
                reason='admin_manual'
            )
            session.add(deleted)
            await session.delete(item)
    await AssortmentService.invalidate_cache()
    referer = request.headers.get("referer")
    if referer:
        return RedirectResponse(url=referer, status_code=303)
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/add")
async def add_item(
    request: Request,
    text: str = Form(...),
    serial: str | None = Form(None),
    category_id: int = Form(...),
    is_booked: bool = Form(False),
    booking_price: float | None = Form(None),
    booking_bonus: float | None = Form(None),
    booking_bonus_reason: str | None = Form(None),
    booking_prepayment: float | None = Form(None),
    booking_platform: str | None = Form(None),
    booking_full_name: str | None = Form(None),
    booking_phone: str | None = Form(None),
    booking_payment_type: str | None = Form(None),
):
    if booking_phone and not validate_phone(booking_phone):
        raise HTTPException(status_code=400, detail="Номер телефона брони должен быть в формате +7XXXXXXXXXX")

    notify_data = None
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        new_item = Item(
            text=text,
            serial=serial.strip().upper() if serial else None,
            category_id=category_id,
            is_booked=is_booked,
            booking_price=booking_price,
            booking_bonus=booking_bonus,
            booking_bonus_reason=booking_bonus_reason,
            booking_prepayment=booking_prepayment,
            booking_platform=booking_platform,
            booking_full_name=booking_full_name,
            booking_phone=booking_phone,
            booking_payment_type=booking_payment_type
        )
        session.add(new_item)
        if is_booked:
            if booking_prepayment and booking_prepayment > 0 and booking_payment_type:
                from bot.models import DailyPayment
                payment = DailyPayment(
                    type='preorder',
                    payment_type=booking_payment_type,
                    amount=booking_prepayment
                )
                session.add(payment)

            notify_data = {
                "item_text": text,
                "serial": serial.strip().upper() if serial else "без серийного номера",
                "price": booking_price,
                "bonus": booking_bonus,
                "bonus_reason": booking_bonus_reason,
                "prepayment": booking_prepayment,
                "platform": booking_platform,
                "full_name": booking_full_name,
                "phone": booking_phone,
                "payment_type": booking_payment_type,
                "is_cancel": False
            }

    if notify_data:
        from .notifications import send_booking_notification
        asyncio.create_task(send_booking_notification(**notify_data))

    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/add_category")
async def add_category(request: Request, name: str = Form(...)):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название не может быть пустым")
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        existing = await session.execute(select(Category.id).where(func.lower(Category.name) == func.lower(name)))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Категория с таким именем уже существует")
        max_order = await session.execute(select(func.coalesce(func.max(Category.sort_order), -1)))
        new_category = Category(name=name, sort_order=max_order.scalar() + 1)
        session.add(new_category)
    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)
