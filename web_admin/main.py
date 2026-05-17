from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

# from bot.middleware.rate_limit import RateLimitMiddleware  # временно отключен

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
# app.add_middleware(RateLimitMiddleware)  # временно отключен

# Авторизация временно отключена по просьбе пользователя
# @app.middleware("http")
# async def auth_middleware(request: Request, call_next):
#     ...

# Роутеры
try:
    from web_admin.routes import auth, clients, dashboard, purchases, assortment, sold, sellers, stats
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
    app.include_router(clients.router, prefix="/clients", tags=["clients"])
    app.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
    app.include_router(assortment.router, prefix="/assortment", tags=["assortment"])
    app.include_router(sold.router, prefix="/sold", tags=["sold"])
    app.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
    app.include_router(stats.router, prefix="/stats", tags=["stats"])
except Exception as e:
    print(f"⚠️ Ошибка подключения роутеров: {e}")

@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")

@app.on_event("startup")
async def startup():
    from bot.config import config
    print(f"🚀 Admin Panel запущен → {config.RENDER_URL}/admin (auth DISABLED)")
