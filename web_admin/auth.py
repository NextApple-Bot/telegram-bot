from datetime import datetime, timedelta
from passlib.context import CryptContext
from starlette.requests import Request

from bot.config import config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str) -> bool:
    """Проверяет пароль."""
    if not config.ADMIN_PASSWORD_HASH:
        return False
    try:
        return pwd_context.verify(plain_password, config.ADMIN_PASSWORD_HASH)
    except Exception:
        return False


def is_authenticated(request: Request) -> bool:
    """Проверяет авторизацию по сессии."""
    if not request.session.get("authenticated"):
        return False

    # Авто-выход через 7 дней
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
