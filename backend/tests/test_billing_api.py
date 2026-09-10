from sqlalchemy import select

from app.core.config import settings
from app.models.billing import CreditLedger, UsageRecord, UserWallet


def register(client, username):
    response = client.post("/api/auth/register", json={
        "email": f"{username}@example.com", "username": username, "password": "secret123"
    })
    assert response.status_code == 201
    token = client.post("/api/auth/login", json={"username": username, "password": "secret123"}).json()["access_token"]
    return response.json()["id"], {"Authorization": f"Bearer {token}"}


def test_register_creates_wallet_and_grant_ledger(client, db):
    user_id, headers = register(client, "alice")
    wallet = db.scalar(select(UserWallet).where(UserWallet.user_id == user_id))
    grant = db.scalar(select(CreditLedger).where(CreditLedger.user_id == user_id, CreditLedger.operation == "grant"))
    assert wallet.balance == settings.BETA_REGISTER_CREDITS
    assert grant.amount == settings.BETA_REGISTER_CREDITS
    assert client.get("/api/me/balance", headers=headers).json()["balance"] == settings.BETA_REGISTER_CREDITS


def test_usage_is_scoped_to_current_user(client, db):
    alice, _ = register(client, "alice")
    bob, bob_headers = register(client, "bob")
    db.add(UsageRecord(user_id=alice, provider="fake", model="m", prompt_tokens=1,
                       completion_tokens=1, total_tokens=2, estimated_cost=0, credits_charged=0,
                       request_id="a-usage", status="charged"))
    db.commit()
    assert client.get("/api/me/usage", headers=bob_headers).json() == []


def test_zero_balance_returns_402_before_ai_call(client, db):
    user_id, headers = register(client, "alice")
    db.query(UserWallet).filter(UserWallet.user_id == user_id).update({"balance": 0})
    db.commit()
    response = client.get("/api/me/balance", headers=headers)
    assert response.status_code == 200
    assert response.json()["balance"] == 0
