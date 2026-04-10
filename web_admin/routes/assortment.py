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
    sale_price: Optional[float] = Form(None),
    sale_prepayment: Optional[float] = Form(None),
    sale_payment_amount: Optional[float] = Form(None),
    sale_payment_type: Optional[str] = Form(None),
    sale_platform: Optional[str] = Form(None),
    sale_full_name: Optional[str] = Form(None),
    sale_phone: Optional[str] = Form(None),
):
    import time
    logger.info(f"🟢 edit_item_submit ВЫЗВАН для item_id={item_id}, is_sold={is_sold}")
    
    # Валидация телефонов
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
            if not sale_payment_amount or sale_payment_amount <= 0:
                raise HTTPException(status_code=400, detail="Укажите сумму оплаты")
            if not sale_payment_type:
                sale_payment_type = "cash"
            
            sale_message_id = -int(time.time() * 1000)
            logger.info(f"Продажа товара {item_id}: цена={sale_price}, оплата={sale_payment_amount}, способ={sale_payment_type}, msg_id={sale_message_id}")

            await send_sale_notification(
                item_text=text,
                price=sale_price,
                payment_type=sale_payment_type,
                prepayment=sale_prepayment if sale_prepayment and sale_prepayment > 0 else None,
                payment_amount=sale_payment_amount,
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
                payment_amount=sale_payment_amount,
                message_id=sale_message_id
            )
            AssortmentService.invalidate_cache()
            return RedirectResponse(url="/admin/assortment", status_code=303)

        # Обновление брони или обычных полей
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
