from uuid import UUID

from fastapi import HTTPException


def test_health_is_lightweight_and_request_id_is_returned(client):
    response = client.get("/health", headers={"X-Request-ID": "not-a-uuid"})
    assert response.json() == {"status": "ok"}
    UUID(response.headers["X-Request-ID"])


def test_valid_request_id_is_inherited(client):
    request_id = "123e4567-e89b-12d3-a456-426614174000"
    response = client.get("/health", headers={"X-Request-ID": request_id})
    assert response.headers["X-Request-ID"] == request_id


def test_ready_skips_optional_redis(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"db": "ok", "redis": "skipped"}}


def test_http_exception_handler_keeps_detail_and_adds_error(client):
    from app.main import app

    @app.get("/_hardening-test-error")
    def error_route():
        raise HTTPException(status_code=409, detail="conflict")

    response = client.get("/_hardening-test-error")
    assert response.status_code == 409
    assert response.json()["detail"] == "conflict"
    assert response.json()["error"]["message"] == "conflict"


def test_rate_limit_returns_unified_429(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_GENERAL", 1)
    assert client.get("/health").status_code == 200
    response = client.get("/health")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_rate_limit_ignores_spoofed_forwarded_headers_by_default(client, monkeypatch):
    # P0-1: without TRUST_PROXY_HEADERS a direct client cannot spoof
    # X-Forwarded-For to rotate buckets; the socket peer is the key.
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_GENERAL", 1)
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", False)
    assert client.get("/health").status_code == 200
    response = client.get("/health", headers={"X-Forwarded-For": "1.2.3.4"})
    assert response.status_code == 429


def test_rate_limit_buckets_by_forwarded_ip_when_trusting_proxy(client, monkeypatch):
    # P0-1: behind a trusted proxy, distinct X-Forwarded-For clients get their
    # own buckets instead of the whole class sharing the proxy IP's bucket.
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_GENERAL", 1)
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    assert client.get("/health", headers={"X-Forwarded-For": "10.0.0.1"}).status_code == 200
    assert client.get("/health", headers={"X-Forwarded-For": "10.0.0.2"}).status_code == 200
