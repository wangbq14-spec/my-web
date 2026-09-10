"""Classroom Beta red-team suite.

Simulates a malicious regular student attacking the running system:
  - IDOR sweep across 9 resource classes (must be 403/404, never 200 with data)
  - /api/admin/* sweep (must be 403 for non-admins)
  - Billing abuse: duplicate/after-the-fact operations must never double-credit
  - Invite abuse: concurrent registrations on a nearly-exhausted code must let
    at most one succeed (transactional semantics)
  - Vision upload security: fake MIME / polyglot magic / oversized / SVG /
    path-traversal filename / empty file / extreme-dimension headers /
    duplicate uploads / cross-user attachment ids
"""

import concurrent.futures
import threading
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.beta import InviteCode, MessageAttachment
from app.models.billing import CreditLedger, UserWallet
from app.models.user import User
from app.services.billing import consume_credit, grant_credit
from app.services.document_tasks import FakeDocumentTaskDispatcher
from app.api.routes import documents as documents_route

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff\xe0"


def _register(client, name, **extra):
    r = client.post("/api/auth/register", json={
        "email": f"{name}@example.com", "username": name,
        "password": "secret123", **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def two_users(client):
    alice = _register(client, "red_alice")
    bob = _register(client, "red_bob")
    alice_token = _login(client, "red_alice")
    bob_token = _login(client, "red_bob")
    return alice, bob, alice_token, bob_token


def test_idor_sweep_conversation_messages_project_document(client, two_users, monkeypatch):
    _, bob, alice_token, bob_token = two_users
    # Keep the document upload out of real Redis/RQ in the test environment.
    monkeypatch.setattr(documents_route, "get_document_task_dispatcher",
                        lambda: FakeDocumentTaskDispatcher())
    # Alice's resources
    conv = client.post("/api/conversations", headers=_h(alice_token),
                       json={"title": "alice-private"}).json()
    proj = client.post("/api/projects", headers=_h(alice_token),
                       json={"name": "alice-project"}).json()
    doc = client.post("/api/documents", headers=_h(alice_token),
                      files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")},
                      data={"project_id": str(proj["id"])}).json()
    checks = [
        ("GET", f"/api/conversations/{conv['id']}", None),
        ("GET", f"/api/conversations/{conv['id']}/messages", None),
        ("PATCH", f"/api/conversations/{conv['id']}", {"title": "hack"}),
        ("DELETE", f"/api/conversations/{conv['id']}", None),
        ("GET", f"/api/projects/{proj['id']}", None),
        ("PATCH", f"/api/projects/{proj['id']}", {"name": "hack"}),
        ("GET", f"/api/projects/{proj['id']}/conversations", None),
        ("GET", f"/api/projects/{proj['id']}/documents", None),
        ("GET", f"/api/documents/{doc['id']}", None),
        ("PATCH", f"/api/documents/{doc['id']}", {"project_id": proj["id"]}),
        ("DELETE", f"/api/documents/{doc['id']}", None),
    ]
    for method, url, payload in checks:
        response = client.request(method, url, headers=_h(bob_token), json=payload)
        assert response.status_code in (403, 404), f"{method} {url} -> {response.status_code} {response.text[:120]}"


def test_idor_workflow_and_artifacts(client, two_users):
    _, bob, alice_token, bob_token = two_users
    # Router prefix is /tasks (see api_router.include_router(workflows.router, prefix="/tasks")).
    created = client.post("/api/tasks", headers=_h(alice_token),
                          json={"title": "alice-flow", "steps": [{"title": "s", "prompt": "p"}]})
    assert created.status_code in (201, 422), created.text
    if created.status_code == 201:
        task_id = created.json()["id"]
        for url in (f"/api/tasks/{task_id}", f"/api/tasks/{task_id}/artifacts"):
            response = client.get(url, headers=_h(bob_token))
            assert response.status_code in (403, 404), f"{url} -> {response.status_code}"
        for action in ("start", "cancel", "retry", "approve", "reject"):
            response = client.post(f"/api/tasks/{task_id}/{action}", headers=_h(bob_token))
            assert response.status_code in (403, 404), f"{action} -> {response.status_code}"


def test_idor_recharge_cancel(client, two_users):
    alice, bob, alice_token, bob_token = two_users
    request = client.post("/api/me/recharge-requests", headers=_h(alice_token),
                          json={"amount_cny": 10})
    assert request.status_code == 201, request.text
    request_id = request.json()["id"]
    # Bob must not cancel Alice's request: the service scopes the state
    # transition by owner, so a foreign cancel touches 0 rows -> 409 (safe,
    # nothing is cancelled, and no ownership/state is leaked as 200).
    assert client.post(f"/api/me/recharge-requests/{request_id}/cancel",
                       headers=_h(bob_token)).status_code in (403, 404, 409)
    # Alice can cancel her own.
    assert client.post(f"/api/me/recharge-requests/{request_id}/cancel",
                       headers=_h(alice_token)).status_code == 200


def test_idor_attachment_download(client, two_users):
    _, bob, alice_token, bob_token = two_users
    upload = client.post("/api/chat/attachments", headers=_h(alice_token),
                         files={"file": ("a.png", PNG_MAGIC + b"data", "image/png")})
    assert upload.status_code == 201, upload.text
    attachment_id = upload.json()["id"]
    assert client.get(f"/api/chat/attachments/{attachment_id}",
                      headers=_h(bob_token)).status_code in (403, 404)
    assert client.get(f"/api/chat/attachments/{attachment_id}",
                      headers=_h(alice_token)).status_code == 200


ADMIN_ENDPOINTS = [
    ("GET", "/api/admin/overview"),
    ("GET", "/api/admin/users"),
    ("GET", "/api/admin/invite-codes"),
    ("GET", "/api/admin/recharge-requests"),
    ("GET", "/api/admin/feedback"),
    ("GET", "/api/admin/analytics"),
    ("POST", "/api/admin/invite-codes"),
    ("POST", "/api/admin/attachments/cleanup-orphans"),
]


@pytest.mark.parametrize("method,url", ADMIN_ENDPOINTS)
def test_admin_endpoints_forbidden_for_regular_user(client, two_users, method, url):
    _, _, _, bob_token = two_users
    if method == "POST":
        payload = {"channel": "classroom", "max_uses": 1}
        if url.endswith("cleanup-orphans"):
            payload = {"before_hours": 24}
        response = client.request(method, url, headers=_h(bob_token), json=payload)
    else:
        response = client.request(method, url, headers=_h(bob_token))
    assert response.status_code == 403, f"{method} {url} -> {response.status_code}"


def test_billing_duplicate_approve_credits_once(client, db, two_users):
    alice, _, alice_token, _ = two_users
    request = client.post("/api/me/recharge-requests", headers=_h(alice_token),
                          json={"amount_cny": 20}).json()
    assert float(request["amount_cny"]) == 20.0
    from app.core.security import create_access_token

    admin_token = create_access_token(subject="1")
    # Grant admin role to user 1 in this test DB.
    admin = db.scalar(select(User).where(User.id == 1))
    admin.role = "admin"
    db.commit()

    first = client.post(f"/api/admin/recharge-requests/{request['id']}/approve",
                        headers=_h(admin_token), json={"note": "once"})
    assert first.status_code in (200, 201), first.text
    wallet = db.scalar(select(UserWallet).where(UserWallet.user_id == alice["id"]))
    ledger = db.scalars(select(CreditLedger).where(CreditLedger.user_id == alice["id"])).all()
    recharge_rows = db.scalars(select(CreditLedger).where(
        CreditLedger.request_id == f"recharge-approve-{request['id']}")).all()
    assert len(recharge_rows) == 1
    credited = sum(entry.amount for entry in ledger)
    assert wallet.balance == credited

    second = client.post(f"/api/admin/recharge-requests/{request['id']}/approve",
                         headers=_h(admin_token), json={"note": "twice"})
    assert second.status_code in (400, 409)
    db.expire_all()
    wallet = db.scalar(select(UserWallet).where(UserWallet.user_id == alice["id"]))
    assert wallet.balance == credited  # no double credit


def test_billing_reject_never_credits_and_cancel_after_approve_blocked(client, db, two_users):
    alice, _, alice_token, _ = two_users
    from app.core.security import create_access_token

    admin = db.scalar(select(User).where(User.id == 1))
    admin.role = "admin"
    db.commit()
    admin_token = create_access_token(subject="1")

    # Reject path: no credit.
    req = client.post("/api/me/recharge-requests", headers=_h(alice_token),
                      json={"amount_cny": 5}).json()
    assert client.post(f"/api/admin/recharge-requests/{req['id']}/reject",
                       headers=_h(admin_token), json={"note": "no"}).status_code == 200
    wallet = db.scalar(select(UserWallet).where(UserWallet.user_id == alice["id"]))
    before = wallet.balance

    # Approve path then cancel must be blocked (no refund double-spend).
    req2 = client.post("/api/me/recharge-requests", headers=_h(alice_token),
                       json={"amount_cny": 8}).json()
    assert client.post(f"/api/admin/recharge-requests/{req2['id']}/approve",
                       headers=_h(admin_token), json={}).status_code in (200, 201)
    cancel = client.post(f"/api/me/recharge-requests/{req2['id']}/cancel",
                         headers=_h(alice_token))
    assert cancel.status_code in (400, 409)
    db.expire_all()
    wallet = db.scalar(select(UserWallet).where(UserWallet.user_id == alice["id"]))
    expected = float(req2.get("credits_requested") or 8.0)
    assert float(wallet.balance) == float(before) + expected  # approved credits only, refund blocked


def test_concurrent_consume_credit_charges_exactly_n_times(db, tmp_path):
    """20 concurrent charges on one wallet must each produce exactly one ledger
    row and deduct exactly the requested total (no double-charge, no lost
    update) — the same-user serialization guard that prevents MySQL 1213."""
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'consume-race.db'}",
        connect_args={"check_same_thread": False},
    )
    Local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    with Local() as session:
        user = User(email="consume_race@example.com", username="consume_race", hashed_password="x")
        session.add(user)
        session.flush()
        grant_credit(session, user.id, 1000, "test seed", request_id="seed")
        session.commit()
        user_id = user.id

    def charge(i):
        with Local() as session:
            try:
                consume_credit(session, user_id, 1, f"consume-{i}", f"race {i}")
                session.commit()
                return "ok"
            except Exception:  # noqa: BLE001
                session.rollback()
                return "failed"

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(charge, range(20)))
    assert results.count("ok") == 20, results
    with Local() as session:
        ledger = session.scalars(select(CreditLedger).where(
            CreditLedger.user_id == user_id, CreditLedger.operation == "consume")).all()
        wallet = session.scalar(select(UserWallet).where(UserWallet.user_id == user_id))
        assert len(ledger) == 20
        assert wallet.balance == 1000 - 20


def test_invite_concurrent_registration_exactly_one_succeeds(tmp_path):
    """max_uses=10, used=9 -> N concurrent registrations, exactly one wins.

    Runs against a file-backed SQLite with one session per request (threads
    share nothing), mirroring the real MySQL serialization semantics.
    """
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'invite-race.db'}",
        connect_args={"check_same_thread": False},
    )
    Local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    with Local() as session:
        session.add(InviteCode(code="RACE-CODE", channel="classroom", max_uses=10, used_count=9))
        session.commit()

    def override_get_db():
        session = Local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    results = []
    barrier = threading.Barrier(5)

    def attempt(index):
        barrier.wait()
        with TestClient(app) as tc:
            response = tc.post("/api/auth/register", json={
                "email": f"race{index}@example.com", "username": f"race_user_{index}",
                "password": "secret123", "invite_code": "RACE-CODE",
            })
            results.append((index, response.status_code))

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    app.dependency_overrides.clear()

    successes = [index for index, status in results if status == 201]
    assert len(successes) == 1, f"expected exactly 1 success, got {results}"
    with Local() as session:
        invite = session.scalar(select(InviteCode).where(InviteCode.code == "RACE-CODE"))
        assert invite.used_count == 10


PNG_HEADER_HUGE = PNG_MAGIC + b"\x00\x00\x00\rIHDR" + (10000).to_bytes(4, "big") + (10000).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00" + b"\x00" * 4


@pytest.mark.parametrize("filename,mime,data,expected", [
    ("evil.exe.jpg", "image/jpeg", b"MZ\x90\x00fake-exe-payload", 415),      # exe bytes as .jpg
    ("fake.png", "image/jpeg", PNG_MAGIC + b"data", 415),                     # MIME/suffix mismatch
    ("virus.svg", "image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg'/>", 415),
    ("empty.png", "image/png", b"", 415),                                     # empty file
    ("../../escape.png", "image/png", PNG_MAGIC + b"data", 400),              # path traversal
    ("..\\escape.png", "image/png", PNG_MAGIC + b"data", 400),
    ("huge.png", "image/png", None, 413),                                     # oversized (built inline)
])
def test_vision_upload_rejects_malicious_files(client, two_users, filename, mime, data, expected):
    _, _, alice_token, _ = two_users
    if data is None:  # keep the >10MB buffer out of the param id / assertion repr
        data = PNG_MAGIC + b"\x00" * (11 * 1024 * 1024)
    response = client.post("/api/chat/attachments", headers=_h(alice_token),
                           files={"file": (filename, BytesIO(data), mime)})
    assert response.status_code == expected, f"{filename} -> {response.status_code} {response.text[:120]}"


def test_vision_extreme_dimension_header_upload_is_harmless(client, two_users):
    _, _, alice_token, _ = two_users
    response = client.post("/api/chat/attachments", headers=_h(alice_token),
                           files={"file": ("wide.png", BytesIO(PNG_HEADER_HUGE), "image/png")})
    # No decode bomb server-side: upload either succeeds (header-only magic check)
    # or is rejected with a clean 4xx; it must never crash with a 500.
    assert response.status_code in (201, 400, 413, 415), response.text


def test_vision_duplicate_upload_creates_distinct_attachments(client, two_users):
    _, _, alice_token, _ = two_users
    payload = ("dup.png", BytesIO(PNG_MAGIC + b"same-bytes"), "image/png")
    first = client.post("/api/chat/attachments", headers=_h(alice_token), files={"file": payload})
    second = client.post("/api/chat/attachments", headers=_h(alice_token), files={"file": payload})
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    for attachment_id in (first.json()["id"], second.json()["id"]):
        assert client.get(f"/api/chat/attachments/{attachment_id}",
                          headers=_h(alice_token)).status_code == 200
