import time
from collections import defaultdict
from typing import Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Простой in-memory rate limiter для админки (можно заменить на Redis в будущем)."""
    def __init__(self, app, calls: int = 10, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.requests: Dict[Tuple[str, str], list] = defaultdict(list)  # (ip, method+path)

    async def dispatch(self, request: Request, call_next):
        # Только для админских эндпоинтов
        if not request.url.path.startswith("/admin"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = (client_ip, request.method + request.url.path)

        now = time.time()
        # Очистка старых записей
        self.requests[key] = [t for t in self.requests[key] if now - t < self.period]

        if len(self.requests[key]) >= self.calls:
            return JSONResponse({"error": "Too many requests"}, status_code=429)

        self.requests[key].append(now)
        response = await call_next(request)
        return response
