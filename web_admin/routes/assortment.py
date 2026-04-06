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
    """
    Отображает таблицу товаров с пагинацией, поиском и фильтром по категориям.
    """
    pool = await get_pool()
    offset = (page - 1) * per_page

    # Базовые части запроса
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

    # Поиск по тексту товара или серийному номеру
    if search:
        search_condition = " AND (i.text ILIKE $" + str(len(params)+1) + " OR i.serial ILIKE $" + str(len(params)+1) + ")"
        base_query += search_condition
        count_query += search_condition
        params.append(f"%{search}%")
        count_params.append(f"%{search}%")

    # Фильтр по категории
    if category_id:
        base_query += " AND i.category_id = $" + str(len(params)+1)
        count_query += " AND i.category_id = $" + str(len(count_params)+1)
        params.append(category_id)
        count_params.append(category_id)

    # Сортировка и пагинация
    base_query += " ORDER BY i.id DESC LIMIT $" + str(len(params)+1) + " OFFSET $" + str(len(params)+2)
    params.append(per_page)
    params.append(offset)

    async with pool.acquire() as conn:
        # Общее количество записей
        total = await conn.fetchval(count_query, *count_params)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        # Список товаров
        rows = await conn.fetch(base_query, *params)
        items = [dict(row) for row in rows]

        # Список категорий для фильтра
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
    })


@router.get("/edit/{item_id}")
async def edit_item_form(request: Request, item_id: int):
    """Форма редактирования одного товара."""
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
):
    """Сохраняет изменения товара."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE items
            SET text = $1, serial = $2, category_id = $3, is_booked = $4
            WHERE id = $5
        """, text, serial.strip().upper() if serial else None, category_id, is_booked, item_id)
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
):
    """Добавляет новый товар вручную."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO items (text, serial, category_id, is_booked)
            VALUES ($1, $2, $3, $4)
        """, text, serial.strip().upper() if serial else None, category_id, is_booked)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)


@router.post("/add_category")
async def add_category(request: Request, name: str = Form(...)):
    """Добавляет новую категорию."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO categories (name) VALUES ($1)", name)
    AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/assortment", status_code=303)
