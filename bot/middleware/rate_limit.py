import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Простой in-memory rate limiter для админки."""
    def __init__(self, app, calls: int = 10, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.requests: dict[tuple[str, str], list] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/admin"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = (client_ip, request.method + request.url.path)

        now = time.time()
        self.requests[key] = [t for t in self.requests[key] if now - t < self.period]

        if len(self.requests[key]) >= self.calls:
            return JSONResponse({"error": "Too many requests"}, status_code=429)

        self.requests[key].append(now)
        return await call_next(request)
