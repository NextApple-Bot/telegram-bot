from starlette.requests import Request

from bot import config

def verify_password(plain_password: str) -> bool:
    """Проверяет пароль (простое сравнение с config.ADMIN_PASSWORD)."""
    return plain_password == config.ADMIN_PASSWORD

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
