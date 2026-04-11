# Пакет для роутов ассортимента
from .views import router as views_router
from .manage import router as manage_router
from .booking import router as booking_router
from .sales import router as sales_router

routers = [views_router, manage_router, booking_router, sales_router]
