from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

from bot.repositories.client_repository import ClientRepository
from web_admin.auth import is_authenticated

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


@router.get("/purchases", response_class=HTMLResponse)
async def purchases_list(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    purchases = await ClientRepository.get_all_purchases_for_export()

    return templates.TemplateResponse("purchases/list.html", {
        "request": request,
        "purchases": purchases,
        "title": "Покупки"
    })


@router.get("/purchases/export")
async def export_purchases(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    file_path = await export_purchases_csv()
    return FileResponse(
        file_path,
        media_type="text/csv",
        filename=f"purchases_{datetime.now().strftime('%Y%m%d')}.csv"
    )


@router.get("/report/full")
async def full_report(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    file_path = await export_full_report_csv()
    return FileResponse(
        file_path,
        media_type="text/csv",
        filename=f"full_report_{datetime.now().strftime('%Y%m%d')}.csv"
    )
