from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from bot.services.assortment import AssortmentService
from web_admin.auth import is_authenticated

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


@router.get("/assortment", response_class=HTMLResponse)
async def assortment_view(
    request: Request,
    search: str = Query(None),
    category_id: int = Query(None),
    per_page: int = Query(50),
    page: int = Query(1)
):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    # Для простоты загружаем все и фильтруем в Python (в реальном проекте лучше SQL)
    all_categories = await AssortmentService.load_inventory()
    
    # Преобразуем в плоский список items для шаблона
    items = []
    for cat in all_categories:
        for item in cat.get("items", []):
            item["category_name"] = cat["name"]
            item["category_id"] = cat["id"]
            items.append(item)

    # Фильтрация
    if search:
        s = search.lower()
        items = [i for i in items if s in i["text"].lower() or (i.get("serial") and s in i["serial"].lower())]
    if category_id:
        items = [i for i in items if i.get("category_id") == category_id]

    total = len(items)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]

    categories_for_filter = [{"id": c["id"], "name": c["name"]} for c in all_categories]

    return templates.TemplateResponse("assortment.html", {
        "request": request,
        "items": page_items,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "search": search,
        "category_id": category_id,
        "categories": categories_for_filter,
        "title": "Ассортимент"
    })


@router.post("/assortment/move_up")
async def move_category_up(request: Request, cat_id: int = Form(...)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    await AssortmentService.move_category_up(cat_id)
    return RedirectResponse("/admin/assortment", status_code=303)


@router.post("/assortment/move_down")
async def move_category_down(request: Request, cat_id: int = Form(...)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    await AssortmentService.move_category_down(cat_id)
    return RedirectResponse("/admin/assortment", status_code=303)


@router.get("/assortment/export")
async def export_assortment(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    categories = await AssortmentService.load_inventory()
    # Простой экспорт
    text = "\n".join([f"{cat['name']}: {len(cat.get('items', []))} товаров" for cat in categories])
    file_path = f"/tmp/assortment_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)
    return FileResponse(
        file_path,
        media_type="text/plain",
        filename=f"assortment_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    )


@router.post("/assortment/reset")
async def reset_assortment(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    await AssortmentService.delete_all_items()
    await AssortmentService.delete_all_categories()

    return RedirectResponse("/admin/assortment", status_code=303)
