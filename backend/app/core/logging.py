import json
import logging
import time
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import settings


def configure_logging():
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO), format="%(message)s", force=True)


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        logging.getLogger("http.access").info(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "level": "info", "request_id": getattr(request.state, "request_id", None), "method": request.method, "path": request.url.path, "status_code": response.status_code, "latency_ms": round((time.perf_counter()-started)*1000, 2), "user_id": getattr(request.state, "user_id", None)}, ensure_ascii=False))
        return response
