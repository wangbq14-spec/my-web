import os

# 必须在导入任何 app.* 之前注入测试环境变量（用独立 SQLite + 测试专用 secret）
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-not-for-production"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["LLM_MODEL"] = "test-default-model"
# 测试环境不连 Redis：dev .env 可能已配置 REDIS_URL，必须在此隔离。
os.environ["REDIS_URL"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.middleware.rate_limit import RateLimitMiddleware  # noqa: E402
from app.models import document, user  # noqa: F401, E402
from app.rag.vector_store import factory as vector_store_factory  # noqa: E402

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def reset_db(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "RAG_UPLOAD_DIR", str(tmp_path / "uploads"))
    # Keep production defaults intact while preventing the app-scoped in-memory
    # limiter from coupling otherwise independent tests. Individual limiter
    # tests can still lower a limit with monkeypatch.
    monkeypatch.setattr(settings, "RATE_LIMIT_GENERAL", 10**9)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH", 10**9)
    monkeypatch.setattr(settings, "RATE_LIMIT_CHAT", 10**9)
    # Tests default to open registration (dev mode); invite-gating scenarios
    # opt in explicitly (see test_invite_register.py).
    monkeypatch.setattr(settings, "INVITE_REQUIRED", False)
    RateLimitMiddleware.reset_all()
    monkeypatch.setattr(vector_store_factory, "SessionLocal", TestSessionLocal)
    vector_store_factory.get_vector_store.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    RateLimitMiddleware.reset_all()
    vector_store_factory.get_vector_store.cache_clear()


@pytest.fixture()
def db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
