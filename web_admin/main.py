from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.gzip import GZipMiddleware

from bot.config import config
from bot.middleware.rate_limit import RateLimitMiddleware
from web_admin.auth import is_authenticated
from web_admin.routes import (
    auth,
    clients,
    dashboard,
    debug,
    purchases,
    sellers,
    sold,
    stats,
)
from web_admin.routes.assortment import manage as assortment_manage
from web_admin.routes.assortment import views as assortment_views

app = FastAPI(
    title="Telegram Bot Admin Panel",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

# Middlewares
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(RateLimitMiddleware, calls=30, period=60)

# Роутеры
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(clients.router, prefix="/clients", tags=["clients"])
app.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
app.include_router(assortment_views.router, prefix="/assortment", tags=["assortment"])
app.include_router(assortment_manage.router, prefix="/assortment", tags=["assortment_manage"])
app.include_router(sold.router, prefix="/sold", tags=["sold"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
app.include_router(debug.router, prefix="/debug", tags=["debug"])


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    if (
        path.startswith("/auth/login")
        or path.startswith("/static")
        or path == "/"
        or path.startswith("/health")
    ):
        return await call_next(request)

    if not is_authenticated(request):
        return RedirectResponse(url="/auth/login")

    return await call_next(request)


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.on_event("startup")
async def startup_event():
    if config.RENDER_URL:
        print(f"🚀 Admin Panel доступен по {config.RENDER_URL}/admin")


@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 Admin Panel остановлен")
