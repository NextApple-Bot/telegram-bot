from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import logging

from bot import config
from .auth import is_authenticated
from .routes import dashboard, clients, purchases, assortment, stats, auth

logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram Bot Admin Panel", prefix="/admin")

# Проверяем наличие секретного ключа
if not config.SECRET_KEY:
    raise ValueError("SECRET_KEY is required for admin panel but not set in environment")
logger.info(f"SECRET_KEY length: {len(config.SECRET_KEY)}")

# Добавляем middleware для сессий
try:
    app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)
    logger.info("SessionMiddleware added successfully")
except Exception as e:
    logger.error(f"Failed to add SessionMiddleware: {e}")
    raise

# Шаблоны
templates = Jinja2Templates(directory="web_admin/templates")

# Подключаем роутеры
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(clients.router, prefix="/clients", tags=["clients"])
app.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
app.include_router(assortment.router, prefix="/assortment", tags=["assortment"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])

# Защита: проверка аутентификации для всех маршрутов, кроме /auth/login
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Исключаем пути, не требующие авторизации
    if request.url.path.startswith("/admin/auth/login") or request.url.path.startswith("/admin/static"):
        return await call_next(request)
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/auth/login")
    return await call_next(request)

# Перенаправление корневого /admin на дашборд
@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")
