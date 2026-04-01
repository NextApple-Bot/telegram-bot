from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette import status

from ..auth import login, logout, is_authenticated

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")

@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    # Если уже аутентифицирован, редирект на дашборд
    if is_authenticated(request):
        return RedirectResponse(url="/admin/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if login(request, password):
        return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid password"})

@router.get("/logout")
async def logout_user(request: Request):
    logout(request)
    return RedirectResponse(url="/admin/auth/login")
