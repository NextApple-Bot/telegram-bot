from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from bot.db import check_db_health, check_redis_health
from web_admin.auth import is_authenticated

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/auth/login")

    db_ok = await check_db_health()
    redis_ok = await check_redis_health()

    context = {
        "request": request,
        "db_status": "✅ Работает" if db_ok else "❌ Проблема",
        "redis_status": "✅ Работает" if redis_ok else "❌ Проблема",
        "bot_token_set": bool(request.app.state.config.BOT_TOKEN),
    }

    return templates.TemplateResponse("dashboard.html", context)
