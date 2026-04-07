# Файл: web_admin/main.py (полностью)
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import logging
import json

from bot import config
from .auth import is_authenticated
from .routes import dashboard, clients, purchases, assortment, stats, auth, sold

logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram Bot Admin Panel")

templates = Jinja2Templates(directory="web_admin/templates")

def safe_fromjson(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Ошибка парсинга JSON: {value[:100]}")
        return []

templates.env.filters["fromjson"] = safe_fromjson

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(clients.router, prefix="/clients", tags=["clients"])
app.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
app.include_router(assortment.router, prefix="/assortment", tags=["assortment"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(sold.router, prefix="/sold", tags=["sold"])

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/admin/auth/login") or request.url.path.startswith("/admin/static"):
        return await call_next(request)
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/auth/login")
    return await call_next(request)

@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")
