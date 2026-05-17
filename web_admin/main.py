from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.gzip import GZipMiddleware

from web_admin.templates import templates

app = FastAPI(title="Telegram Bot Admin Panel")
app.add_middleware(GZipMiddleware, minimum_size=500)

# Роутеры (с защитой)
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

safe_include("web_admin.routes.dashboard", "/dashboard", ["dashboard"])
safe_include("web_admin.routes.clients", "/clients", ["clients"])
safe_include("web_admin.routes.purchases", "/purchases", ["purchases"])
safe_include("web_admin.routes.sold", "/sold", ["sold"])
safe_include("web_admin.routes.stats", "/stats", ["stats"])
safe_include("web_admin.routes.sellers", "/sellers", ["sellers"])
safe_include("web_admin.routes.auth", "/auth", ["auth"])
safe_include("web_admin.routes.debug", "/debug", ["debug"])
safe_include("web_admin.routes.assortment.views", "/assortment", ["assortment"])
safe_include("web_admin.routes.assortment.manage", "/assortment", ["assortment_manage"])

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    return await call_next(request)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Прямой дашборд без редиректа
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "target_date": "17.05.2026",
        "target_date_iso": "2026-05-17",
        "sales_today": 12,
        "revenue_today": 245000,
        "payments": {"cash": 45000, "terminal": 120000, "qr": 35000, "transfer": 25000, "invoice": 10000, "installment": 10000},
        "total_revenue": 245000,
        "plan_amount": 600000,
        "stats": {"sales_count": 12, "preorders_count": 3, "bookings_count": 2},
        "sellers": [{"id": 1, "name": "Алексей", "present": True}, {"id": 2, "name": "Мария", "present": False}],
        "chart_dates": ["11.05", "12.05", "13.05", "14.05", "15.05", "16.05", "17.05"],
        "chart_sales": [8, 12, 15, 10, 18, 14, 12],
        "chart_revenue": [145000, 210000, 265000, 180000, 320000, 255000, 245000],
        "top_labels": [],
        "top_counts": [],
        "days": 7,
    })

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.on_event("startup")
async def startup():
    print("🚀 Admin Panel запущен (auth DISABLED)")
