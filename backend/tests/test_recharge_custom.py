"""Custom-amount recharge: server-side pricing, snapshots, tamper and idempotency."""

import json

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token
from app.models.beta import RechargeRequest
from app.models.billing import CreditLedger, UserWallet
from app.models.user import User


@pytest.fixture()
def actors(db):
    users = [User(username=name, email=f"{name}@example.com", hashed_password="unused",
                  role=role) for name, role in [("admin", "admin"), ("alice", "user"), ("bob", "user")]]
    db.add_all(users)
    db.commit()
    return [(u.id, {"Authorization": f"Bearer {create_access_token(subject=str(u.id))}"}) for u in users]


def quote(client, actors, amount):
    return client.post("/api/me/recharge-quote", headers=actors[1][1], json={"amount_cny": amount})


def test_custom_quote_valid(client, actors):
    response = quote(client, actors, "10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["amount_cny"] == "10"
    assert payload["credits"] == 3000
    assert payload["pricing_version"] == "v1"
    assert payload["expires_at"]


@pytest.mark.parametrize("amount", ["0.5", "501", "0", "-1", "NaN", "Infinity"])
def test_custom_quote_rejects_invalid_amounts(client, actors, amount):
    assert quote(client, actors, amount).status_code == 422


def test_custom_quote_requires_auth(client):
    assert client.post("/api/me/recharge-quote", json={"amount_cny": "10"}).status_code == 401


def test_custom_quote_disabled(client, actors, monkeypatch):
    monkeypatch.setattr(settings, "CUSTOM_RECHARGE_ENABLED", False)
    assert quote(client, actors, "10").status_code == 403


def test_custom_submit_computes_credits_server_side(client, db, actors):
    response = client.post("/api/me/recharge-requests", headers=actors[1][1],
                           json={"amount_cny": "10"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["credits_requested"] == 3000
    assert payload["package_code"] == "custom"
    assert payload["amount_display"] == "10 CNY"
    assert str(payload["amount_cny"]).startswith("10")
    snapshot = json.loads(payload["pricing_snapshot"])
    assert snapshot["pricing_version"] == "v1"
    assert snapshot["rate_per_cny"] == "300"
    assert snapshot["credits"] == 3000
    row = db.get(RechargeRequest, payload["id"])
    assert row.amount_cny == pytest.approx(10, abs=0.01) or str(row.amount_cny).startswith("10")


def test_custom_submit_rejects_client_supplied_credits(client, actors):
    response = client.post("/api/me/recharge-requests", headers=actors[1][1],
                           json={"amount_cny": "10", "credits_requested": 999999})
    assert response.status_code == 422


def test_custom_submit_rejects_both_and_neither(client, actors):
    both = client.post("/api/me/recharge-requests", headers=actors[1][1],
                       json={"package_code": "experience", "credits_requested": 1000, "amount_cny": "10"})
    assert both.status_code == 422
    neither = client.post("/api/me/recharge-requests", headers=actors[1][1], json={})
    assert neither.status_code == 422


def test_custom_submit_disabled(client, actors, monkeypatch):
    monkeypatch.setattr(settings, "CUSTOM_RECHARGE_ENABLED", False)
    response = client.post("/api/me/recharge-requests", headers=actors[1][1],
                           json={"amount_cny": "10"})
    assert response.status_code == 403


def test_fixed_package_submit_still_works(client, actors):
    response = client.post("/api/me/recharge-requests", headers=actors[1][1],
                           json={"package_code": "experience", "credits_requested": 1000})
    assert response.status_code == 201
    assert response.json()["credits_requested"] == 1000
    assert response.json()["amount_cny"] is None


def test_custom_approve_grants_once_with_ledger(client, db, actors):
    request = client.post("/api/me/recharge-requests", headers=actors[1][1],
                          json={"amount_cny": "10"}).json()
    url = f"/api/admin/recharge-requests/{request['id']}/approve"
    assert client.post(url, headers=actors[0][1]).status_code == 200
    # Double approve (duplicate HTTP + concurrent guard) must grant only once.
    assert client.post(url, headers=actors[0][1]).status_code == 409
    entries = db.scalars(select(CreditLedger).where(CreditLedger.user_id == actors[1][0])).all()
    assert len(entries) == 1
    assert entries[0].amount == 3000
    assert entries[0].request_id == f"recharge-approve-{request['id']}"
    assert db.scalar(select(UserWallet.balance).where(UserWallet.user_id == actors[1][0])) == 3000


def test_ordinary_user_cannot_approve(client, actors):
    request = client.post("/api/me/recharge-requests", headers=actors[1][1],
                          json={"amount_cny": "10"}).json()
    url = f"/api/admin/recharge-requests/{request['id']}/approve"
    assert client.post(url, headers=actors[1][1]).status_code == 403


def test_admin_sees_custom_amount(client, actors):
    request = client.post("/api/me/recharge-requests", headers=actors[1][1],
                          json={"amount_cny": "12.00"}).json()
    listing = client.get("/api/admin/recharge-requests", headers=actors[0][1]).json()
    row = next(item for item in listing if item["id"] == request["id"])
    assert str(row["amount_cny"]).startswith("12")
    assert row["credits_requested"] == 3600
    assert row["pricing_snapshot"] is not None


def test_payment_info_includes_custom_recharge(client, actors):
    payload = client.get("/api/me/payment-info", headers=actors[1][1]).json()
    custom = payload["custom_recharge"]
    assert custom["enabled"] is True
    assert custom["min_cny"] == "1"
    assert custom["max_cny"] == "500"
    assert custom["step_cny"] == "1"
    assert custom["credit_per_cny"] == "300"
    assert custom["pricing_version"] == "v1"
