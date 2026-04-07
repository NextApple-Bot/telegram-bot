# Файл: web_admin/routes/assortment.py
from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import logging
import re
from datetime import date

from bot.services.assortment import AssortmentService
from bot.repositories import ItemRepository, StatsRepository
from bot.utils.validators import extract_serials
from bot.db import get_pool
from bot import config
from aiogram import Bot

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

ALLOWED_SORT_FIELDS = {
    "id": "i.id",
    "text": "i.text",
    "serial": "i.serial",
    "category_name": "c.name",
    "is_booked": "i.is_booked",
    "created_at": "i.created_at",
}


def format_number(value: float) -> str:
    """Форматирует число с пробелом как разделитель тысяч."""
    if value is None:
        return ""
    return f"{value:,.0f}".replace(",", " ")


def validate_phone(phone: str) -> bool:
    """Проверяет, что номер телефона имеет формат +7XXXXXXXXXX (ровно 12 символов)."""
    if not phone:
        return True
    return bool(re.match(r'^\+7\d{10}$', phone))


async def send_booking_notification(
    item_text: str,
    serial: str,
    price: float = None,
    prepayment: float = None,
    platform: str = None,
    full_name: str = None,
    phone: str = None,
    is_cancel: bool = False
):
    """Уведомление о брони (без дублирования серийного номера)."""
    try:
        bot = Bot(token=config.TOKEN)
        if is_cancel:
            message_text = f"❌ Отмена Брони:\n\n{item_text}"
        else:
            remainder = 0
            if price and prepayment:
                remainder = price - prepayment
            lines = ["БРОНЬ:\n", item_text]
            if price is not None:
                lines.append(f"Стоимость – {format_number(price)}")
            lines.append("")
            lines.append("")
            if prepayment is not None:
                lines.append(f"П/О – {format_number(prepayment)}")
            if price is not None and prepayment is not None:
                lines.append(f"Остаток – {format_number(remainder)}")
                lines.append(f"Общая – {format_number(price)}")
            lines.append("")
            lines.append("")
            if full_name:
                lines.append(full_name)
            if phone:
                lines.append(phone)
            lines.append("")
            if platform:
                lines.append(f"Площадка – {platform}")
            message_text = "\n".join(lines)
        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=message_text,
            message_thread_id=config.THREAD_PREORDER
        )
        await bot.session.close()
        logger.info(f"✅ Уведомление о брони отправлено: {item_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления о брони: {e}")


async def send_sale_notification(
    item_text: str,
    price: float,                # полная стоимость товара
    payment_type: str,           # способ оплаты текущего платежа (cash, terminal, ...)
    prepayment: float = None,    # П/О (предоплата, уже внесённая ранее)
    payment_amount: float = None, # Оплата (сумма, которую клиент внёс сейчас)
    platform: str = None,
    full_name: str = None,
    phone: str = None,
):
    """
    Уведомление о продаже в топик «Продажи».
    Формат:
    - Стоимость – X
    - Пустая строка
    - <Способ оплаты на русском> – Z   (где Z = оплата)
    - Общая – Y                         (где Y = П/О + оплата)
    - Пустые строки
    - ФИО, телефон, площадка
    """
    try:
        bot = Bot(token=config.TOKEN)
        payment_type_ru = {
            'cash': 'Наличными', 'terminal': 'Терминал', 'qr': 'QR-код',
            'transfer': 'Перевод', 'invoice': 'Оплата по счету', 'installment': 'Рассрочка'
        }.get(payment_type, payment_type)

        lines = [item_text]
        # Стоимость
        lines.append(f"Стоимость – {format_number(price)}")
        # Пустая строка после стоимости
        lines.append("")
        # Строка оплаты: "<Способ оплаты> – <Оплата>"
        paid_amount = payment_amount if payment_amount is not None else 0
        lines.append(f"{payment_type_ru} – {format_number(paid_amount)}")
        # Общая = П/О + оплата
        total_paid = (prepayment or 0) + paid_amount
        lines.append(f"Общая – {format_number(total_paid)}")
        # Пустые строки после блока сумм
        lines.append("")
        lines.append("")
        if full_name:
            lines.append(full_name)
        if phone:
            lines.append(phone)
        lines.append("")
        if platform:
            lines.append(f"Площадка – {platform}")

        message_text = "\n".join(lines)
        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=message_text,
            message_thread_id=config.THREAD_SALES
        )
        await bot.session.close()
        logger.info(f"✅ Уведомление о продаже отправлено: {item_text}")
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления о продаже: {e}")


async def delete_item_and_log_sale(
    item_id: int,
    text: str,
    serial: str,
    category_id: int,
    price: float,
    prepayment: float,
    payment_type: str,
    payment_amount: float,
    message_id: int = None
):
    """Удаляет товар, сохраняет в deleted_items, добавляет статистику продаж и финансы."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Сохраняем в deleted_items
            await conn.execute("""
                INSERT INTO deleted_items (item_id, text, serial, category_id, reason)
                VALUES ($1, $2, $3, $4, 'sale_from_admin')
            """, item_id, text, serial, category_id)
            # Удаляем товар
            await conn.execute("DELETE FROM items WHERE id = $1", item_id)
            # Добавляем статистику продажи (используем payment_amount как сумму продажи)
            await StatsRepository.add_sale(
                count=1,
                cash=payment_type == 'cash' and payment_amount or 0,
                terminal=payment_type == 'terminal' and payment_amount or 0,
                qr=payment_type == 'qr' and payment_amount or 0,
                transfer=payment_type == 'transfer' and payment_amount or 0,
                invoice=payment_type == 'invoice' and payment_amount or 0,
                installment=payment_type == 'installment' and payment_amount or 0,
                is_accessory=False,
                message_id=message_id,
                conn=conn
            )
            # Добавляем финансовую запись (daily_payments) – сумма текущего платежа
            await conn.execute("""
                INSERT INTO daily_payments (type, payment_type, amount)
                VALUES ('sale', $1, $2)
            """, payment_type, payment_amount)


@router.get("/", response_class=HTMLResponse)
async def list_assortment(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    sort_by: str = Query("id", regex="^(id|text|serial|category_name|is_booked|created_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
):
    pool = await get_pool()
    offset = (page - 1) * per_page

    category_id_int = None
    if category_id and category_id.isdigit():
        category_id_int = int(category_id)

    sort_column = ALLOWED_SORT_FIELDS.get(sort_by, "i.id")
    order_direction = "DESC" if sort_order == "desc" else "ASC"

    base_query = f"""
        SELECT i.id, i.text, i.serial, i.is_booked, i.created_at,
               c.id as category_id, c.name as category_name
        FROM items i
        JOIN categories c ON i.category_id = c.id
        WHERE 1=1
    """
    count_query = "SELECT COUNT(*) FROM items i WHERE 1=1"
    params = []
    count_params = []

    if search:
        search_condition = " AND (i.text ILIKE $" + str(len(params)+1) + " OR i.serial ILIKE $" + str(len(params)+1) + ")"
        base_query += search_condition
        count_query += search_condition
        params.append(f"%{search}%")
        count_params.append(f"%{search}%")

    if category_id_int is not None:
        base_query += " AND i.category_id = $" + str(len(params)+1)
        count_query += " AND i.category_id = $" + str(len(count_params)+1)
        params.append(category_id_int)
        count_params.append(category_id_int)

    base_query += f" ORDER BY {sort_column} {order_direction} LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
    params.append(per_page)
    params.append(offset)

    async with pool.acquire() as conn:
        total = await conn.fetchval(count_query, *count_params)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        rows = await conn.fetch(base_query, *params)
        items = [dict(row) for row in rows]
        categories_rows = await conn.fetch("SELECT id, name FROM categories ORDER BY name")
        categories = [{"id": row["id"], "name": row["name"]} for row in categories_rows]

    return templates.TemplateResponse("assortment.html", {
        "request": request,
        "items": items,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total,
        "search": search,
        "category_id": category_id,
        "categories": categories,
        "sort_by": sort_by,
        "sort_order": sort_order,
    })


@router.get("/search")
async def search_items(q: str = Query(..., min_length=2)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT i.id, i.text, i.serial, c.name as category_name
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE i.text ILIKE $1 OR i.serial ILIKE $1
            ORDER BY i.id DESC
            LIMIT 10
        ''', f'%{q}%')
    results = [{"id": r["id"], "text": r["text"], "serial": r["serial"], "category": r["category_name"]} for r in rows]
    return {"results": results}


@router.get("/edit/{item_id}")
async def edit_item_form(request: Request, item_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT i.id, i.text, i.serial, i.is_booked, i.created_at,
                   c.id as category_id, c.name as category_name,
                   i.booking_price, i.booking_prepayment, i.booking_platform,
                   i.booking_full_name, i.booking_phone,
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
    # Бронь
    booking_price: Optional[float] = Form(None),
    booking_prepayment: Optional[float] = Form(None),
    booking_platform: Optional[str] = Form(None),
    booking_full_name: Optional[str] = Form(None),
    booking_phone: Optional[str] = Form(None),
    # Продажа
    sale_price: Optional[float] = Form(None),
    sale_prepayment: Optional[float] = Form(None),
    sale_payment_amount: Optional[float] = Form(None),
    sale_payment_type: Optional[str] = Form(None),
    sale_platform: Optional[str] = Form(None),
    sale_full_name: Optional[str] = Form(None),
    sale_phone: Optional[str] = Form(None),
):
    # Валидация номеров телефона
    if booking_phone and not validate_phone(booking_phone):
        raise HTTPException(status_code=400, detail="Номер телефона брони должен быть в формате +7XXXXXXXXXX")
    if sale_phone and not validate_phone(sale_phone):
        raise HTTPException(status_code=400, detail="Номер телефона продажи должен быть в формате +7XXXXXXXXXX")

    pool = await get_pool()
    async with pool.acquire() as conn:
        old = await conn.fetchrow("SELECT is_sold, text, serial, category_id FROM items WHERE id = $1", item_id)
        if not old:
            raise HTTPException(status_code=404, detail="Item not found")
        old_is_sold = old["is_sold"]
        old_text = old["text"]
        old_serial = old["serial"] or ""
        old_category_id = old["category_id"]

        if old_is_sold:
            raise HTTPException(status_code=400, detail="Товар уже продан, редактирование невозможно")

        if is_sold:
            if not sale_price:
                raise HTTPException(status_code=400, detail="Укажите стоимость продажи")
            if not sale_payment_type:
                sale_payment_type = "cash"
            if sale_payment_amount is None:
                sale_payment_amount = 0
            # Отправляем уведомление в топик продаж
            await send_sale_notification(
                item_text=text,
                price=sale_price,
                payment_type=sale_payment_type,
                prepayment=sale_prepayment if sale_prepayment and sale_prepayment > 0 else None,
                payment_amount=sale_payment_amount if sale_payment_amount > 0 else None,
                platform=sale_platform,
                full_name=sale_full_name,
                phone=sale_phone
            )
            await delete_item_and_log_sale(
                item_id=item_id,
                text=old_text,
                serial=old_serial,
                category_id=old_category_id,
                price=sale_price,
                prepayment=sale_prepayment or 0,
                payment_type=sale_payment_type,
                payment_amount=sale_payment_amount or 0
            )
            AssortmentService.invalidate_cache()
            return RedirectResponse(url="/admin/assortment", status_code=303)

        # Иначе – обновляем обычные поля или бронь
        await conn.execute("""
            UPDATE items
            SET text = $1, serial = $2, category_id = $3, is_booked = $4,
                booking_price = $5, booking_prepayment = $6, booking_platform = $7,
                booking_full_name = $8, booking_phone = $9,
                sale_price = NULL, sale_prepayment = NULL, sale_payment_type = NULL,
                sale_platform = NULL, sale_full_name = NULL, sale_phone = NULL,
                sale_payment_amount = NULL, is_sold = FALSE
            WHERE id = $10
        """, text, serial.strip().upper() if serial else None, category_id, is_booked,
           booking_price, booking_prepayment, booking_platform,
           booking_full_name, booking_phone, item_id)

        old_is_booked = await conn.fetchval("SELECT is_booked FROM items WHERE id = $1", item_id)
        if not old_is_booked and is_booked:
            await send_booking_notification(
                item_text=text,
                serial=serial.strip().upper() if serial else "без серийного номера",
                price=booking_price,
                prepayment=booking_prepayment,
                platform=booking_platform,
                full_name=booking_full_name,
                phone=booking_phone,
                is_cancel=False
            )
        elif old_is_booked and not is_booked:
            await send_booking_notification(
                item_text=old_text,
                serial=old_serial,
                is_cancel=True
            )

    AssortmentService.invalidate_cache()
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
    AssortmentService.invalidate_cache()
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
):
    # Валидация номера телефона
    if booking_phone and not validate_phone(booking_phone):
        raise HTTPException(status_code=400, detail="Номер телефона брони должен быть в формате +7XXXXXXXXXX")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO items (text, serial, category_id, is_booked,
                               booking_price, booking_prepayment, booking_platform,
                               booking_full_name, booking_phone)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, text, serial.strip().upper() if serial else None, category_id, is_booked,
           booking_price, booking_prepayment, booking_platform,
           booking_full_name, booking_phone)
        if is_booked:
            await send_booking_notification(
                item_text=text,
                serial=serial.strip().upper() if serial else "без серийного номера",
                price=booking_price,
                prepayment=booking_prepayment,
                platform=booking_platform,
                full_name=booking_full_name,
                phone=booking_phone,
                is_cancel=False
            )
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/add_category")
async def add_category(request: Request, name: str = Form(...)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO categories (name) VALUES ($1)", name)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)
