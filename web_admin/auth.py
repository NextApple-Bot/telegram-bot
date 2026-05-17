from datetime import datetime, timedelta
from starlette.requests import Request

from bot.config import config


def verify_password(plain_password: str) -> bool:
    """Проверяет пароль (простое сравнение)."""
    if not config.ADMIN_PASSWORD:
        return False
    return plain_password == config.ADMIN_PASSWORD


def is_authenticated(request: Request) -> bool:
    """Проверяет авторизацию по сессии."""
    if "session" not in getattr(request, "scope", {}):
        return False

    try:
        if not request.session.get("authenticated"):
            return False

        login_time_str = request.session.get("login_time")
        if login_time_str:
            try:
                login_time = datetime.fromisoformat(login_time_str)
                if datetime.utcnow() - login_time > timedelta(days=7):
                    request.session.clear()
                    return False
            except Exception:
                request.session.clear()
                return False

        return True
    except Exception:
        return False


def login_user(request: Request, password: str) -> bool:
    """Выполняет вход."""
    if verify_password(password):
        request.session["authenticated"] = True
        request.session["login_time"] = datetime.utcnow().isoformat()
        return True
    return False


def logout_user(request: Request):
    """Выход из системы."""
    request.session.clear()
