from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from bot.config import config
from bot.middleware.rate_limit import RateLimitMiddleware
from web_admin.auth import is_authenticated
from web_admin.routes import auth, clients, dashboard, purchases, assortment

app = FastAPI(
    title="Bot Admin Panel",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Middlewares
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(RateLimitMiddleware)   # исправлено: правильный класс

# Роутеры
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(clients.router, prefix="/clients", tags=["clients"])
app.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
app.include_router(assortment.router, prefix="/assortment", tags=["assortment"])


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith(("/auth/login", "/static", "/health")) or path == "/":
        return await call_next(request)

    if not is_authenticated(request):
        return RedirectResponse(url="/admin/auth/login")

    return await call_next(request)


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")


@app.on_event("startup")
async def startup():
    print(f"🚀 Admin Panel запущен → {config.RENDER_URL}/admin")
