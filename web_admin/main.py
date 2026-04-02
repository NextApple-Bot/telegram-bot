from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from bot import config
from .auth import is_authenticated
from .routes import dashboard, clients, purchases, assortment, stats, auth

app = FastAPI(title="Telegram Bot Admin Panel")

# Подключаем middleware для сессий
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)

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
    if request.url.path.startswith("/admin/auth/login") or request.url.path.startswith("/admin/static"):
        return await call_next(request)
    if not is_authenticated(request):
        return RedirectResponse(url="/admin/auth/login")
    return await call_next(request)

# Перенаправление корневого /admin на дашборд
@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")
