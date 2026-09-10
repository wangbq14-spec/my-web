from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from redis import Redis

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import APIError, api_error_handler, http_error_handler
from app.core.logging import AccessLogMiddleware, configure_logging
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.db.session import engine
from fastapi import HTTPException

configure_logging()

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(HTTPException, http_error_handler)

app.include_router(api_router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    # Readiness: fail closed. Check MySQL and Redis independently so a
    # failure is attributed to the correct dependency (no false positives).
    checks = {"db": "ok", "redis": "ok"}
    failures: list[str] = []

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        checks["db"] = "failed"
        failures.append("db")

    if settings.REDIS_URL:
        try:
            client = Redis.from_url(
                settings.REDIS_URL,
                protocol=2,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            client.close()
        except Exception:
            checks["redis"] = "failed"
            failures.append("redis")
    else:
        # Redis is deliberately optional for the API process (opened lazily on
        # task dispatch); report it honestly instead of faking readiness.
        checks["redis"] = "skipped"

    if failures:
        raise HTTPException(status_code=503, detail=f"{', '.join(failures)} unavailable")
    return {"status": "ready", "checks": checks}
