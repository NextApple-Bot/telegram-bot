# Файл: web_admin/main.py
import json
import logging
from datetime import date, datetime

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware

from .auth import is_authenticated
from .routes import auth, clients, dashboard, debug, purchases, sellers, sold, stats
from .routes.assortment import manage as assortment_manage
from .routes.assortment import views as assortment_views

logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram Bot Admin Panel")

app.add_middleware(GZipMiddleware, minimum_size=500)

templates = Jinja2Templates(directory="web_admin/templates")


def safe_fromjson(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError, AttributeError):
        logger.warning(f"Ошибка парсинга JSON: {value[:100] if isinstance(value, str) else value}")
        return []


templates.env.filters["fromjson"] = safe_fromjson


def format_date_filter(value, fmt="%d.%m.%Y"):
    """Форматирует дату/время в строку указанного формата. По умолчанию ДД.ММ.ГГГГ."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime(fmt)
    if isinstance(value, str):
        for fmt_in in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
            try:
                dt = datetime.strptime(value, fmt_in)
                return dt.strftime(fmt)
            except ValueError:
                continue
    return str(value)


templates.env.filters["format_date"] = format_date_filter


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(clients.router, prefix="/clients", tags=["clients"])
app.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
app.include_router(assortment_views.router, prefix="/assortment", tags=["assortment"])
app.include_router(assortment_manage.router, prefix="/assortment", tags=["assortment_manage"])
app.include_router(sold.router, prefix="/sold", tags=["sold"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
app.include_router(debug.router, prefix="/admin", tags=["debug"])


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
