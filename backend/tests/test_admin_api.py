"""Admin and recharge API contracts. DSH runs these tests."""

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.billing import CreditLedger, UsageRecord, UserWallet
from app.models.beta import RechargeRequest
from app.models.user import User
from app.services import billing


@pytest.fixture()
def actors(db):
    users = [User(username=name, email=f"{name}@example.com", hashed_password="unused",
                  role=role) for name, role in [("admin", "admin"), ("alice", "user"), ("bob", "user")]]
    db.add_all(users)
    db.commit()
    return [(u.id, {"Authorization": f"Bearer {create_access_token(subject=str(u.id))}"}) for u in users]


@pytest.mark.parametrize("method,path,payload", [
    ("get", "/users", None), ("get", "/users/1", None),
    ("post", "/users/1/grant-credits", {"amount": 1, "reason": "test"}),
    ("get", "/invite-codes", None),
    ("post", "/invite-codes", {"channel": "class", "max_uses": 2}),
    ("post", "/invite-codes/1/disable", None),
    ("get", "/recharge-requests", None),
    ("post", "/recharge-requests/1/approve", None),
    ("post", "/recharge-requests/1/reject", {"note": "no"}),
])
def test_admin_rejects_ordinary_users(client, actors, method, path, payload):
    assert client.request(method, f"/api/admin{path}", headers=actors[1][1], json=payload).status_code == 403


def test_user_summary_and_search(client, db, actors):
    uid, _ = actors[1]
    db.add(UserWallet(user_id=uid, balance=120))
    for i, credits in enumerate([3, 7]):
        db.add(UsageRecord(user_id=uid, provider="test", model="test", prompt_tokens=1,
                           completion_tokens=1, total_tokens=2, estimated_cost=0,
                           credits_charged=credits, request_id=f"usage-{i}"))
    db.commit()
    response = client.get("/api/admin/users?search=alice&limit=1&offset=0", headers=actors[0][1])
    assert response.status_code == 200
    summary = response.json()[0]
    assert summary["balance"] == 120
    assert summary["usage_count"] == 2
    assert summary["credits_charged"] == 10
    assert summary["is_active"] is True
    assert "hashed_password" not in summary
    assert client.get(f"/api/admin/users/{uid}", headers=actors[0][1]).json() == summary
    assert client.get("/api/admin/users?offset=99", headers=actors[0][1]).json() == []
    assert client.get("/api/admin/users/9999", headers=actors[0][1]).status_code == 404
    empty = client.get(f"/api/admin/users/{actors[2][0]}", headers=actors[0][1]).json()
    assert (empty["balance"], empty["usage_count"], empty["credits_charged"]) == (0, 0, 0)


def test_grant_ledger_idempotency_and_audit(client, db, actors):
    uid, _ = actors[1]
    url = f"/api/admin/users/{uid}/grant-credits"
    payload = {"amount": 50, "reason": "class reward", "request_id": "reward-1"}
    for _ in range(2):
        response = client.post(url, headers=actors[0][1], json=payload)
        assert response.status_code == 200
        assert response.json()["balance"] == 50
    ledger = db.scalars(select(CreditLedger).where(CreditLedger.user_id == uid)).all()
    assert len(ledger) == 1
    assert ledger[0].operation == "grant" and ledger[0].amount == 50
    assert "admin" in ledger[0].description and "class reward" in ledger[0].description
    assert client.post(url, headers=actors[0][1], json={**payload, "amount": 51}).status_code == 409
    for amount in [0, -1, True, 1.5]:
        assert client.post(url, headers=actors[0][1], json={**payload, "amount": amount}).status_code == 422


def test_invite_create_list_disable(client, actors):
    headers = actors[0][1]
    payload = {"channel": "class", "max_uses": 2, "expires_at": "2099-01-01T08:00:00+08:00"}
    first = client.post("/api/admin/invite-codes", headers=headers, json=payload)
    second = client.post("/api/admin/invite-codes", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["code"].startswith("OMNIXA-AI-")
    assert first.json()["code"] != second.json()["code"]
    assert first.json()["created_by"] == actors[0][0]
    assert first.json()["expires_at"] == "2099-01-01T00:00:00"
    assert len(client.get("/api/admin/invite-codes", headers=headers).json()) == 2
    result = client.post(f"/api/admin/invite-codes/{first.json()['id']}/disable", headers=headers)
    assert result.status_code == 200 and result.json()["is_active"] is False


def submit(client, headers):
    response = client.post("/api/me/recharge-requests", headers=headers,
                           json={"package_code": "experience", "credits_requested": 1000, "note": "paid"})
    assert response.status_code == 201
    return response.json()


def test_recharge_submission_ownership_cancel(client, actors):
    request = submit(client, actors[1][1])
    assert request["status"] == "pending" and request["amount_display"]
    listed = client.get("/api/me/recharge-requests", headers=actors[1][1]).json()
    assert len(listed) == 1
    # The listing now carries an additive `username` field; compare core fields.
    for key in ("id", "user_id", "package_code", "amount_display", "credits_requested", "status"):
        assert listed[0][key] == request[key]
    assert client.get("/api/me/recharge-requests", headers=actors[2][1]).json() == []
    url = f"/api/me/recharge-requests/{request['id']}/cancel"
    assert client.post(url, headers=actors[2][1]).status_code == 409
    assert client.post(url, headers=actors[1][1]).json()["status"] == "cancelled"
    assert client.post(url, headers=actors[1][1]).status_code == 409
    assert client.post(f"/api/admin/recharge-requests/{request['id']}/approve", headers=actors[0][1]).status_code == 409


@pytest.mark.parametrize("payload", [
    {"package_code": "unknown", "credits_requested": 1000},
    {"package_code": "experience", "credits_requested": 6000},
    {"package_code": "experience", "credits_requested": 1000, "amount_display": "0.01"},
])
def test_recharge_rejects_tampered_packages(client, actors, payload):
    assert client.post("/api/me/recharge-requests", headers=actors[1][1], json=payload).status_code == 422


def test_approve_only_once_with_ledger(client, db, actors):
    request = submit(client, actors[1][1])
    url = f"/api/admin/recharge-requests/{request['id']}/approve"
    response = client.post(url, headers=actors[0][1])
    assert response.status_code == 200
    assert response.json()["reviewed_by"] == actors[0][0]
    assert response.json()["reviewed_at"]
    assert client.post(url, headers=actors[0][1]).status_code == 409
    entries = db.scalars(select(CreditLedger).where(CreditLedger.user_id == actors[1][0])).all()
    assert len(entries) == 1 and entries[0].amount == 1000
    assert entries[0].request_id == f"recharge-approve-{request['id']}"
    assert db.scalar(select(UserWallet.balance).where(UserWallet.user_id == actors[1][0])) == 1000
    assert client.get("/api/admin/recharge-requests?status=pending", headers=actors[0][1]).json() == []
    assert len(client.get("/api/admin/recharge-requests?status=approved", headers=actors[0][1]).json()) == 1


def test_reject_never_grants(client, db, actors):
    request = submit(client, actors[1][1])
    url = f"/api/admin/recharge-requests/{request['id']}"
    response = client.post(f"{url}/reject", headers=actors[0][1], json={"note": "not received"})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert "paid" in response.json()["note"] and "not received" in response.json()["note"]
    assert client.post(f"{url}/reject", headers=actors[0][1], json={}).status_code == 409
    assert client.post(f"{url}/approve", headers=actors[0][1]).status_code == 409
    assert db.scalars(select(CreditLedger)).all() == []


def test_approve_rolls_back_status_and_wallet_on_grant_failure(client, db, actors, monkeypatch):
    request = submit(client, actors[1][1])
    original = billing.grant_credit

    def fail_after_grant(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected failure after ledger flush")

    monkeypatch.setattr(billing, "grant_credit", fail_after_grant)
    with pytest.raises(RuntimeError, match="injected failure"):
        client.post(f"/api/admin/recharge-requests/{request['id']}/approve", headers=actors[0][1])
    db.expire_all()
    assert db.get(RechargeRequest, request["id"]).status == "pending"
    assert db.scalars(select(CreditLedger)).all() == []
    assert db.scalars(select(UserWallet)).all() == []
