import hashlib
import hmac
from typing import Optional
from starlette.requests import Request
from starlette.responses import Response
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext

from bot import config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str) -> bool:
    """Проверяет пароль (сравнивает с хешем из config.ADMIN_PASSWORD)."""
    # Предполагаем, что ADMIN_PASSWORD уже сохранён как хеш bcrypt
    # Для простоты можно хранить открытый пароль, но лучше хеш.
    # В config.py будем хешировать при загрузке, если это не хеш.
    return pwd_context.verify(plain_password, config.ADMIN_PASSWORD)

def hash_password(password: str) -> str:
    """Возвращает хеш пароля для bcrypt."""
    return pwd_context.hash(password)

def is_authenticated(request: Request) -> bool:
    """Проверяет, есть ли пользователь в сессии."""
    return request.session.get("authenticated", False)

def login(request: Request, password: str) -> bool:
    """Выполняет вход, если пароль верен."""
    if verify_password(password):
        request.session["authenticated"] = True
        return True
    return False

def logout(request: Request) -> None:
    """Завершает сессию."""
    request.session.clear()
