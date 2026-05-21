from datetime import datetime, timedelta
from starlette.requests import Request

from bot.config import config


def verify_password(plain_password: str) -> bool:
    # Временно отключена проверка пароля (как ты просил)
    return True


def login_user(request: Request, username: str = "admin"):
    request.session["user"] = username
    request.session["login_time"] = datetime.now().isoformat()


def logout_user(request: Request):
    request.session.clear()


def is_authenticated(request: Request) -> bool:
    return request.session.get("user") is not None
