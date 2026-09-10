import time
import uuid
from collections import defaultdict, deque
from weakref import WeakSet

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


def _client_ip(request) -> str:
    """Resolve the client IP for rate-limit bucketing.

    Behind a trusted reverse proxy (nginx) every socket peer is the proxy, so
    trust the leftmost X-Forwarded-For / X-Real-IP only when the operator has
    opted in via TRUST_PROXY_HEADERS. Otherwise fall back to the socket peer so
    a direct client cannot spoof the header to rotate buckets and bypass the
    limiter.
    """
    if settings.TRUST_PROXY_HEADERS:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
        xri = request.headers.get("x-real-ip")
        if xri and xri.strip():
            return xri.strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    _instances = WeakSet()

    def __init__(self, app):
        super().__init__(app)
        self._windows = defaultdict(deque)
        self._instances.add(self)

    def reset(self):
        self._windows.clear()

    @classmethod
    def reset_all(cls):
        for instance in cls._instances:
            instance.reset()

    async def dispatch(self, request, call_next):
        path = request.url.path
        limit = settings.RATE_LIMIT_GENERAL
        if path.startswith("/api/auth/"):
            limit = settings.RATE_LIMIT_AUTH
        elif path.startswith("/api/feedback"):
            limit = settings.RATE_LIMIT_FEEDBACK
        elif path.endswith("/chat") or path.endswith("/chat/stream") or "/agent/" in path or path.startswith("/api/tasks") or path.startswith("/api/documents"):
            limit = settings.RATE_LIMIT_CHAT
        key = (_client_ip(request), path.split("/")[2] if path.startswith("/api/") else path)
        now = time.monotonic()
        window = self._windows[key]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= limit:
            message = "\u8bf7\u6c42\u8fc7\u4e8e\u9891\u7e41\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5"
            request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
            request.state.request_id = request_id
            response = JSONResponse(
                {
                    "error": {"code": "RATE_LIMITED", "message": message, "request_id": request_id},
                    "detail": message,
                },
                status_code=429,
            )
            response.headers["X-Request-ID"] = request_id
            return response
        window.append(now)
        return await call_next(request)
