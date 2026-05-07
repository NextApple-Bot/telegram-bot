import re

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select

from bot.db import get_async_session_factory
from bot.services.assortment import AssortmentService
from bot.models import Item, Category
from web_admin.templates import templates

router = APIRouter()

ALLOWED_SORT_FIELDS = {
    "id": Item.id,
    "text": Item.text,
    "serial": Item.serial,
    "category_name": Category.name,
    "is_booked": Item.is_booked,
    "created_at": Item.created_at,
}


@router.get("/", response_class=HTMLResponse)
async def list_assortment(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str | None = Query(None),
    category_id: str | None = Query(None),
    sort_by: str = Query("id", pattern="^(id|text|serial|category_name|is_booked|created_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    async_session = get_async_session_factory()
    async with async_session() as session:
        offset = (page - 1) * per_page

        base_query = select(Item.id, Item.text, Item.serial, Item.is_booked, Item.created_at,
                            Category.id.label('category_id'), Category.name.label('category_name')) \
            .join(Category, Item.category_id == Category.id) \
            .where(Category.name != '__SYSTEM__')

        count_query = select(func.count()).select_from(Item).join(Category, Item.category_id == Category.id) \
            .where(Category.name != '__SYSTEM__')

        if search:
            base_query = base_query.where(
                (Item.text.ilike(f"%{search}%")) | (Item.serial.ilike(f"%{search}%"))
            )
            count_query = count_query.where(
                (Item.text.ilike(f"%{search}%")) | (Item.serial.ilike(f"%{search}%"))
            )

        if category_id and category_id.isdigit():
            base_query = base_query.where(Item.category_id == int(category_id))
            count_query = count_query.where(Item.category_id == int(category_id))

        sort_column = ALLOWED_SORT_FIELDS.get(sort_by, Item.id)
        order_direction = sort_column.desc() if sort_order == "desc" else sort_column.asc()
        base_query = base_query.order_by(order_direction).limit(per_page).offset(offset)

        total = (await session.execute(count_query)).scalar()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        items = (await session.execute(base_query)).all()

        # Категории для фильтра
        categories_q = select(Category.id, Category.name).where(Category.name != '__SYSTEM__')
        if (await session.execute(select(True).select_from(Category).where(Column('sort_order').isnot(None)))).scalar():
            categories_q = categories_q.order_by(Category.sort_order, Category.name)
        else:
            categories_q = categories_q.order_by(Category.name)
        categories = (await session.execute(categories_q)).all()

    return templates.TemplateResponse("assortment.html", {
        "request": request,
        "items": [{"id": i.id, "text": i.text, "serial": i.serial, "is_booked": i.is_booked,
                   "created_at": i.created_at, "category_id": i.category_id, "category_name": i.category_name} for i in items],
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total,
        "search": search,
        "category_id": category_id,
        "categories": [{"id": c.id, "name": c.name} for c in categories],
        "sort_by": sort_by,
        "sort_order": sort_order,
    })


# ... остальные эндпоинты без изменений (search, search_by_serial, move_up, move_down, delete, rename, reorder)
# Вставьте их из актуального файла, здесь приведу полностью для экономии места
# Они не содержат устаревших конструкций

@router.get("/search")
async def search_items(q: str = Query(..., min_length=2)):
    async_session = get_async_session_factory()
    async with async_session() as session:
        result = await session.execute(
            select(Item.id, Item.text, Item.serial, Category.name.label('category_name'))
            .join(Category, Item.category_id == Category.id)
            .where((Item.text.ilike(f'%{q}%')) | (Item.serial.ilike(f'%{q}%')))
            .order_by(Item.id.desc())
            .limit(10)
        )
        rows = result.all()
    return {"results": [{"id": r.id, "text": r.text, "serial": r.serial, "category": r.category_name} for r in rows]}


@router.get("/api/search_by_serial")
async def search_by_serial(q: str = Query(..., min_length=1)):
    normalized_q = re.sub(r'[№\s]', '', q.strip())
    if len(normalized_q) < 1:
        return {"results": []}
    async_session = get_async_session_factory()
    async with async_session() as session:
        result = await session.execute(
            select(Item.id, Item.text, Item.serial, Item.sale_price, Category.name.label('category_name'))
            .join(Category, Item.category_id == Category.id)
            .where(func.regexp_replace(Item.serial, '[№\\s]', '', 'g').ilike(f'%{normalized_q}%'))
            .order_by(Item.id)
            .limit(10)
        )
        rows = result.all()
    results = []
    for r in rows:
        price = r.sale_price
        if price is None:
            match = re.search(r'(\d[\d\s]*[.,]?\d*)\s*(?:₽|руб)', r.text)
            if match:
                price_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    price = float(price_str)
                except ValueError:
                    price = None
        results.append({"id": r.id, "text": r.text, "serial": r.serial, "price": price, "category": r.category_name})
    return {"results": results}


@router.post("/categories/{cat_id}/move_up")
async def move_category_up(cat_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        current = await session.get(Category, cat_id)
        if not current:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        prev = (await session.execute(
            select(Category).where(Category.sort_order < current.sort_order, Category.name != '__SYSTEM__')
            .order_by(Category.sort_order.desc()).limit(1)
        )).scalar_one_or_none()
        if prev:
            prev_order, cur_order = prev.sort_order, current.sort_order
            await session.execute(
                f"UPDATE categories SET sort_order = {cur_order} WHERE id = {prev.id}"
            )
            await session.execute(
                f"UPDATE categories SET sort_order = {prev_order} WHERE id = {cat_id}"
            )
    await AssortmentService.invalidate_cache()
    return JSONResponse({"success": True})


@router.post("/categories/{cat_id}/move_down")
async def move_category_down(cat_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        current = await session.get(Category, cat_id)
        if not current:
            raise HTTPException(status_code=404, detail="Категория не найдена")
        next_cat = (await session.execute(
            select(Category).where(Category.sort_order > current.sort_order, Category.name != '__SYSTEM__')
            .order_by(Category.sort_order.asc()).limit(1)
        )).scalar_one_or_none()
        if next_cat:
            next_order, cur_order = next_cat.sort_order, current.sort_order
            await session.execute(
                f"UPDATE categories SET sort_order = {cur_order} WHERE id = {next_cat.id}"
            )
            await session.execute(
                f"UPDATE categories SET sort_order = {next_order} WHERE id = {cat_id}"
            )
    await AssortmentService.invalidate_cache()
    return JSONResponse({"success": True})


@router.post("/categories/{cat_id}/delete")
async def delete_category(cat_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        cat = await session.get(Category, cat_id)
        if not cat or cat.name == '__SYSTEM__':
            raise HTTPException(status_code=400, detail="Нельзя удалить эту категорию")
        count = (await session.execute(select(func.count()).where(Item.category_id == cat_id))).scalar()
        if count > 0:
            raise HTTPException(status_code=400, detail="Категория не пуста")
        await session.delete(cat)
    await AssortmentService.invalidate_cache()
    return JSONResponse({"success": True})


@router.post("/categories/{cat_id}/rename")
async def rename_category(cat_id: int, new_name: str = Query(..., min_length=1)):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        cat = await session.get(Category, cat_id)
        if not cat or cat.name == '__SYSTEM__':
            raise HTTPException(status_code=400, detail="Нельзя переименовать эту категорию")
        dup = (await session.execute(
            select(Category.id).where(func.lower(Category.name) == func.lower(new_name), Category.id != cat_id)
        )).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=400, detail="Категория с таким именем уже существует")
        cat.name = new_name
        session.add(cat)
    await AssortmentService.invalidate_cache()
    return JSONResponse({"success": True})


@router.post("/categories/reorder")
async def reorder_categories(order: list[int]):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        for idx, cat_id in enumerate(order):
            cat = await session.get(Category, cat_id)
            if cat:
                cat.sort_order = idx
                session.add(cat)
    await AssortmentService.invalidate_cache()
    return JSONResponse({"success": True})
