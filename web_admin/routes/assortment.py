# Файл: web_admin/routes/assortment.py
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
    # Принудительно преобразуем items в список, если это не список
    for cat in categories:
        if not isinstance(cat.get('items'), list):
            cat['items'] = []
    # Добавляем id категории и id товаров
    pool = await get_pool()
    async with pool.acquire() as conn:
        for cat in categories:
            row = await conn.fetchrow('SELECT id FROM categories WHERE name = $1', cat['header'])
            cat['id'] = row['id'] if row else None
            # Получаем товары с их ID для этой категории
            if cat['id']:
                items_rows = await conn.fetch('SELECT id, text FROM items WHERE category_id = $1 ORDER BY id', cat['id'])
                cat['items_with_ids'] = [dict(row) for row in items_rows]
            else:
                cat['items_with_ids'] = []
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
    items_text: list[str] = Form(...)
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('UPDATE categories SET name = $1 WHERE id = $2', name, category_id)
            await conn.execute('DELETE FROM items WHERE category_id = $1', category_id)
            for line in items_text:
                if line and line.strip():
                    line = line.strip()
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

# ========== НОВЫЕ ЭНДПОИНТЫ ДЛЯ РУЧНОГО ДОБАВЛЕНИЯ/УДАЛЕНИЯ ТОВАРОВ ==========

@router.post("/add_item/{category_id}")
async def add_item_to_category(request: Request, category_id: int, item_text: str = Form(...)):
    """Добавляет один товар в указанную категорию."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        serials = extract_serials(item_text)
        serial = serials[0].upper() if serials else None
        is_booked = 'Бронь от' in item_text
        await conn.execute('''
            INSERT INTO items (text, serial, category_id, is_booked)
            VALUES ($1, $2, $3, $4)
        ''', item_text, serial, category_id, is_booked)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url=f"/admin/assortment/edit/{category_id}", status_code=303)

@router.post("/delete_item/{item_id}")
async def delete_item(request: Request, item_id: int):
    """Удаляет товар по ID с сохранением в deleted_items."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow('SELECT text, serial, category_id FROM items WHERE id = $1', item_id)
            if row:
                # Сохраняем в deleted_items
                await conn.execute('''
                    INSERT INTO deleted_items (item_id, text, serial, category_id, reason)
                    VALUES ($1, $2, $3, $4, 'admin_manual')
                ''', item_id, row['text'], row['serial'], row['category_id'])
                # Удаляем товар
                await conn.execute('DELETE FROM items WHERE id = $1', item_id)
    AssortmentService.invalidate_cache()
    # Возвращаемся на предыдущую страницу (список категорий или редактирование)
    referer = request.headers.get("referer")
    if referer:
        return RedirectResponse(url=referer, status_code=303)
    return RedirectResponse(url="/admin/assortment", status_code=303)
