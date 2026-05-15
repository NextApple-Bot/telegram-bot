from passlib.context import CryptContext
from starlette.requests import Request

from bot.config import config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str) -> bool:
    """Проверяет пароль против bcrypt-хэша из настроек."""
    if not config.ADMIN_PASSWORD_HASH:
        return False
    try:
        return pwd_context.verify(plain_password, config.ADMIN_PASSWORD_HASH)
    except Exception:
        return False


def is_authenticated(request: Request) -> bool:
    """Проверяет, авторизован ли пользователь в сессии."""
    return request.session.get("authenticated", False)


def login(request: Request, password: str) -> bool:
    """Выполняет вход и устанавливает сессию."""
    if verify_password(password):
        request.session["authenticated"] = True
        request.session["login_time"] = str(__import__("datetime").datetime.utcnow())
        return True
    return False


def logout(request: Request) -> None:
    """Выход из системы."""
    request.session.clear()
