from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

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
#     path = request.url.path
#     if "/auth/login" in path or path.startswith("/static") or path.startswith("/health") or path == "/":
#         return await call_next(request)
#     if not is_authenticated(request):
#         return RedirectResponse(url="/admin/auth/login")
#     return await call_next(request)

@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")

@app.on_event("startup")
async def startup():
    from bot.config import config
    print(f"🚀 Admin Panel запущен → {config.RENDER_URL}/admin (auth disabled)")
