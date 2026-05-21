from datetime import datetime, timedelta
from starlette.requests import Request
from passlib.context import CryptContext

from bot.config import config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str) -> bool:
    if not config.ADMIN_PASSWORD_HASH:
        return False
    return pwd_context.verify(plain_password, config.ADMIN_PASSWORD_HASH)

def login_user(request: Request, username: str = "admin"):
    request.session["user"] = username
    request.session["login_time"] = datetime.now().isoformat()

def logout_user(request: Request):
    request.session.clear()

def is_authenticated(request: Request) -> bool:
    return request.session.get("user") is not None
