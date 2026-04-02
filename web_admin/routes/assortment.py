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
    items_text: list[str] = Form(...)
):
    # items_text — список значений из всех input[name="items_text"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Обновляем название категории
            await conn.execute('UPDATE categories SET name = $1 WHERE id = $2', name, category_id)
            # Удаляем все старые товары
            await conn.execute('DELETE FROM items WHERE category_id = $1', category_id)
            # Добавляем новые товары из списка (только непустые строки)
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

# Остальные методы (add_category, delete_category) остаются без изменений
