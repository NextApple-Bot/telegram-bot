from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI(title="NextStore Admin")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SessionMiddleware, secret_key="change-this-secret-key-2026")

templates = Jinja2Templates(directory="web_admin/templates")

from web_admin.routes import auth, dashboard, assortment, clients, purchases, sellers, stats

app.include_router(auth.router, prefix="/admin/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/admin", tags=["dashboard"])
app.include_router(assortment.router, prefix="/admin/assortment", tags=["assortment"])
app.include_router(clients.router, prefix="/admin/clients", tags=["clients"])
app.include_router(purchases.router, prefix="/admin/purchases", tags=["purchases"])
app.include_router(sellers.router, prefix="/admin/sellers", tags=["sellers"])
app.include_router(stats.router, prefix="/admin/stats", tags=["stats"])

@app.get("/")
async def root():
    return RedirectResponse(url="/admin/auth/login")

@app.get("/health")
async def health():
    return {"status": "ok"}
