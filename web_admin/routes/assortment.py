# Файл: web_admin/routes/assortment.py
from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from bot.services.assortment import AssortmentService
from bot.repositories import ItemRepository
from bot.utils.validators import extract_serials
from bot.db import get_pool

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


@router.get("/", response_class=HTMLResponse)
async def list_assortment(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
):
    """Отображает ассортимент в виде таблицы с пагинацией, поиском и фильтром по категории."""
    pool = await get_pool()
    offset = (page - 1) * per_page

    # Базовый запрос с JOIN для получения имени категории
    base_query = """
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
        search_term = f"%{search}%"
        base_query += " AND (i.text ILIKE $" + str(len(params)+1) + " OR i.serial ILIKE $" + str(len(params)+2) + ")"
        params.extend([search_term, search_term])
        count_query += " AND (text ILIKE $" + str(len(count_params)+1) + " OR serial ILIKE $" + str(len(count_params)+2) + ")"
        count_params.extend([search_term, search_term])

    if category_id:
        base_query += " AND i.category_id = $" + str(len(params)+1)
        params.append(category_id)
        count_query += " AND category_id = $" + str(len(count_params)+1)
        count_params.append(category_id)

    base_query += " ORDER BY i.id DESC LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
    params.append(per_page)
    params.append(offset)

    async with pool.acquire() as conn:
        total = await conn.fetchval(count_query, *count_params)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        rows = await conn.fetch(base_query, *params)
        items = [dict(row) for row in rows]

    # Получаем список всех категорий для фильтра
    categories_rows = await conn.fetch("SELECT id, name FROM categories ORDER BY name")
    categories = [dict(row) for row in categories_rows]

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
    })


@router.get("/edit/{item_id}")
async def edit_item_form(request: Request, item_id: int):
    """Форма редактирования отдельного товара."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT i.id, i.text, i.serial, i.is_booked, c.id as category_id, c.name as category_name
            FROM items i
            JOIN categories c ON i.category_id = c.id
            WHERE i.id = $1
        """, item_id)
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        item = dict(row)

        categories = await conn.fetch("SELECT id, name FROM categories ORDER BY name")
        categories = [dict(cat) for cat in categories]

    return templates.TemplateResponse("assortment_edit_item.html", {
        "request": request,
        "item": item,
        "categories": categories,
    })


@router.post("/edit/{item_id}")
async def edit_item_submit(
    request: Request,
    item_id: int,
    text: str = Form(...),
    serial: Optional[str] = Form(None),
    category_id: int = Form(...),
    is_booked: bool = Form(False),
):
    """Сохраняет изменения товара."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE items
            SET text = $1, serial = $2, category_id = $3, is_booked = $4
            WHERE id = $5
        """, text, serial, category_id, is_booked, item_id)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/delete/{item_id}")
async def delete_item(request: Request, item_id: int):
    """Удаляет товар с сохранением в deleted_items."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT text, serial, category_id FROM items WHERE id = $1", item_id)
            if row:
                await conn.execute("""
                    INSERT INTO deleted_items (item_id, text, serial, category_id, reason)
                    VALUES ($1, $2, $3, $4, 'admin_manual')
                """, item_id, row['text'], row['serial'], row['category_id'])
                await conn.execute("DELETE FROM items WHERE id = $1", item_id)
    AssortmentService.invalidate_cache()
    referer = request.headers.get("referer")
    if referer:
        return RedirectResponse(url=referer, status_code=303)
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.get("/add")
async def add_item_form(request: Request):
    """Форма добавления нового товара."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        categories = await conn.fetch("SELECT id, name FROM categories ORDER BY name")
        categories = [dict(cat) for cat in categories]
    return templates.TemplateResponse("assortment_add_item.html", {
        "request": request,
        "categories": categories,
    })


@router.post("/add")
async def add_item_submit(
    request: Request,
    text: str = Form(...),
    serial: Optional[str] = Form(None),
    category_id: int = Form(...),
    is_booked: bool = Form(False),
):
    """Добавляет новый товар."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO items (text, serial, category_id, is_booked)
            VALUES ($1, $2, $3, $4)
        """, text, serial, category_id, is_booked)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.get("/categories")
async def list_categories(request: Request):
    """Управление категориями (отдельная страница)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.id, c.name, COUNT(i.id) as item_count
            FROM categories c
            LEFT JOIN items i ON c.id = i.category_id
            GROUP BY c.id
            ORDER BY c.name
        """)
        categories = [dict(row) for row in rows]
    return templates.TemplateResponse("assortment_categories.html", {
        "request": request,
        "categories": categories,
    })


@router.post("/categories/add")
async def add_category(request: Request, name: str = Form(...)):
    """Добавляет новую категорию."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO categories (name) VALUES ($1)", name)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment/categories", status_code=303)


@router.post("/categories/delete/{category_id}")
async def delete_category(request: Request, category_id: int):
    """Удаляет категорию, только если она пуста."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM items WHERE category_id = $1", category_id)
        if count > 0:
            raise HTTPException(status_code=400, detail="Category is not empty")
        await conn.execute("DELETE FROM categories WHERE id = $1", category_id)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment/categories", status_code=303)
