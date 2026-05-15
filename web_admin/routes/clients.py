from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.repositories.client_repository import ClientRepository
from web_admin.auth import is_authenticated

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


@router.get("/clients", response_class=HTMLResponse)
async def clients_list(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    clients = await ClientRepository.get_all_clients_for_export()

    return templates.TemplateResponse("clients/list.html", {
        "request": request,
        "clients": clients,
        "title": "Клиенты"
    })


@router.get("/clients/export")
async def export_clients(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    file_path = await export_clients_csv()  # из service_commands
    return FileResponse(
        file_path,
        media_type="text/csv",
        filename=f"clients_{datetime.now().strftime('%Y%m%d')}.csv"
    )
