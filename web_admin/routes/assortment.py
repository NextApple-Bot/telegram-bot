from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from bot.services.assortment import AssortmentService
from web_admin.auth import is_authenticated

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


@router.get("/assortment", response_class=HTMLResponse)
async def assortment_view(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    categories = await AssortmentService.load_inventory()

    return templates.TemplateResponse("assortment.html", {
        "request": request,
        "categories": categories,
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
    text = await build_output_text(categories)   # из bot/utils/sort.py

    file_path = await save_temp_file(text, suffix=".txt")
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
