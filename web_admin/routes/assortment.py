from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from bot.services.assortment import AssortmentService
from bot.repositories import ItemRepository
from bot.utils.validators import extract_serials
from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/", response_class=HTMLResponse)
async def list_assortment(request: Request):
    categories = await AssortmentService.load_inventory()
    return templates.TemplateResponse("assortment.html", {"request": request, "categories": categories})

@router.get("/edit/{category_id}")
async def edit_category_form(request: Request, category_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        cat = await conn.fetchrow('SELECT * FROM categories WHERE id = $1', category_id)
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        items = await conn.fetch('SELECT * FROM items WHERE category_id = $1 ORDER BY id', category_id)
    return templates.TemplateResponse("assortment_edit.html", {
        "request": request,
        "category": dict(cat),
        "items": [dict(item) for item in items]
    })

@router.post("/edit/{category_id}")
async def edit_category_submit(
    request: Request,
    category_id: int,
    name: str = Form(...),
    items_text: str = Form(...)
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('UPDATE categories SET name = $1 WHERE id = $2', name, category_id)
            await conn.execute('DELETE FROM items WHERE category_id = $1', category_id)
            lines = [line.strip() for line in items_text.splitlines() if line.strip()]
            for line in lines:
                serials = extract_serials(line)
                serial = serials[0].upper() if serials else None
                is_booked = 'Бронь от' in line
                await conn.execute('''
                    INSERT INTO items (text, serial, category_id, is_booked)
                    VALUES ($1, $2, $3, $4)
                ''', line, serial, category_id, is_booked)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)

@router.post("/add_category")
async def add_category(request: Request, name: str = Form(...)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('INSERT INTO categories (name) VALUES ($1)', name)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)

@router.post("/delete_category/{category_id}")
async def delete_category(request: Request, category_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval('SELECT COUNT(*) FROM items WHERE category_id = $1', category_id)
        if count > 0:
            raise HTTPException(status_code=400, detail="Category not empty")
        await conn.execute('DELETE FROM categories WHERE id = $1', category_id)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)

# ========== НОВЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С ОТДЕЛЬНЫМИ ТОВАРАМИ ==========
@router.post("/item/{item_id}/edit")
async def edit_item(
    request: Request,
    item_id: int,
    text: str = Form(...),
    serial: str = Form(None)
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            UPDATE items SET text = $1, serial = $2 WHERE id = $3
        ''', text, serial.strip().upper() if serial else None, item_id)
    AssortmentService.invalidate_cache()
    # Перенаправляем обратно на страницу редактирования категории
    # Нужно знать category_id – получим его из товара
    row = await conn.fetchrow('SELECT category_id FROM items WHERE id = $1', item_id)
    if row:
        category_id = row['category_id']
        return RedirectResponse(url=f"/admin/assortment/edit/{category_id}", status_code=303)
    return RedirectResponse(url="/admin/assortment", status_code=303)

@router.post("/item/{item_id}/delete")
async def delete_item(request: Request, item_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Получим category_id перед удалением для редиректа
        row = await conn.fetchrow('SELECT category_id FROM items WHERE id = $1', item_id)
        category_id = row['category_id'] if row else None
        await conn.execute('DELETE FROM items WHERE id = $1', item_id)
    AssortmentService.invalidate_cache()
    if category_id:
        return RedirectResponse(url=f"/admin/assortment/edit/{category_id}", status_code=303)
    return RedirectResponse(url="/admin/assortment", status_code=303)

@router.post("/category/{category_id}/add_item")
async def add_item_to_category(
    request: Request,
    category_id: int,
    text: str = Form(...),
    serial: str = Form(None)
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        is_booked = 'Бронь от' in text
        await conn.execute('''
            INSERT INTO items (text, serial, category_id, is_booked)
            VALUES ($1, $2, $3, $4)
        ''', text, serial.strip().upper() if serial else None, category_id, is_booked)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url=f"/admin/assortment/edit/{category_id}", status_code=303)
