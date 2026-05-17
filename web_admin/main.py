from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.gzip import GZipMiddleware

app = FastAPI(title="Telegram Bot Admin Panel")
app.add_middleware(GZipMiddleware, minimum_size=500)

# Роутеры (с защитой от ошибок импорта)
def safe_include(module_path: str, prefix: str, tags: list):
    try:
        module = __import__(module_path, fromlist=["router"])
        if hasattr(module, "router"):
            app.include_router(module.router, prefix=prefix, tags=tags)
            print(f"✅ {prefix} подключен")
        else:
            print(f"⚠️ {prefix} не имеет router")
    except Exception as e:
        print(f"❌ {prefix} ошибка: {e}")

# Основные роутеры
safe_include("web_admin.routes.dashboard", "/dashboard", ["dashboard"])
safe_include("web_admin.routes.clients", "/clients", ["clients"])
safe_include("web_admin.routes.purchases", "/purchases", ["purchases"])
safe_include("web_admin.routes.sold", "/sold", ["sold"])
safe_include("web_admin.routes.stats", "/stats", ["stats"])
safe_include("web_admin.routes.sellers", "/sellers", ["sellers"])
safe_include("web_admin.routes.auth", "/auth", ["auth"])
safe_include("web_admin.routes.debug", "/debug", ["debug"])

# Ассортимент (может быть проблемным)
safe_include("web_admin.routes.assortment.views", "/assortment", ["assortment"])
safe_include("web_admin.routes.assortment.manage", "/assortment", ["assortment_manage"])

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Авторизация временно отключена
    return await call_next(request)

@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")

@app.on_event("startup")
async def startup():
    print("🚀 Admin Panel запущен (auth DISABLED, safe imports)")
