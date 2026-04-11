# Пакет для роутов ассортимента
from .views import router as views_router
from .manage import router as manage_router

# Можно экспортировать роутеры для удобства, но в main.py мы импортируем напрямую
__all__ = ['views_router', 'manage_router']
