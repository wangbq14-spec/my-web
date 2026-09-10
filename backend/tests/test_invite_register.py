import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.routes import auth
from app.core.config import settings
from app.models.beta import InviteCode
from app.models.billing import CreditLedger, UserWallet
from app.models.user import User


@pytest.fixture(autouse=True)
def beta_settings(monkeypatch):
    monkeypatch.setattr(settings, "INVITE_REQUIRED", False)
    monkeypatch.setattr(settings, "BETA_REGISTER_CREDITS", 2000)
    monkeypatch.setattr(settings, "REFERRAL_REWARD_CREDITS", 100)
    monkeypatch.setattr(settings, "REFERRAL_NEW_USER_CREDITS", 50)


def register(client, name="alice", **extra):
    return client.post("/api/auth/register", json={
        "email": f"{name}@example.com", "username": name,
        "password": "secret123", **extra,
    })


def balance(db, uid):
    db.expire_all()
    return db.scalar(select(UserWallet.balance).where(UserWallet.user_id == uid))


def test_required_invite_and_dev_bypass(client, db, monkeypatch):
    monkeypatch.setattr(settings, "INVITE_REQUIRED", True)
    assert register(client).status_code == 400
    assert register(client, invite_code="missing").status_code == 400
    invite = InviteCode(code="BETA", channel="test", max_uses=1)
    db.add(invite)
    db.commit()
    assert register(client, invite_code="BETA").status_code == 201
    db.refresh(invite)
    assert invite.used_count == 1
    assert register(client, "bobby", invite_code="BETA").status_code == 400
    monkeypatch.setattr(settings, "INVITE_REQUIRED", False)
    # A provided code is always validated, even when registration is not gated.
    assert register(client, "bobby", invite_code="missing").status_code == 400
    assert register(client, "carol").status_code == 201


def test_provided_invite_is_consumed_when_not_required(client, db):
    invite = InviteCode(code="CLASS-A", channel="classroom", max_uses=5)
    db.add(invite)
    db.commit()
    response = register(client, invite_code="CLASS-A")
    assert response.status_code == 201
    db.refresh(invite)
    assert invite.used_count == 1
    assert register(client, "bobby", invite_code="CLASS-A").status_code == 201
    db.refresh(invite)
    assert invite.used_count == 2


def test_expired_invite_rejected_even_when_not_required(client, db, monkeypatch):
    from datetime import timedelta

    from app.models.user import utcnow_naive

    invite = InviteCode(code="OLD", channel="classroom", max_uses=5,
                        expires_at=utcnow_naive() - timedelta(days=1))
    db.add(invite)
    db.commit()
    assert register(client, invite_code="OLD").status_code == 400


def test_beta_grant_and_duplicate_registration_are_idempotent(client, db):
    response = register(client)
    assert response.status_code == 201
    uid = response.json()["id"]
    assert balance(db, uid) == 2000
    assert register(client).status_code == 400
    user = db.get(User, uid)
    auth._grant_registration_credits(db, user)
    assert balance(db, uid) == 2000
    entries = db.scalars(select(CreditLedger).where(CreditLedger.user_id == uid)).all()
    assert len(entries) == 1
    assert entries[0].request_id == f"beta-register-{uid}"


def test_referral_rewards_are_single_level_and_idempotent(client, db):
    first = register(client).json()["id"]
    inviter = db.get(User, first)
    response = register(client, "bobby", referral_code=inviter.referral_code)
    assert response.status_code == 201
    second = response.json()["id"]
    user = db.get(User, second)
    assert user.referred_by_user_id == first
    assert user.referral_code and user.referral_code != inviter.referral_code
    auth._grant_registration_credits(db, user)
    assert balance(db, first) == 2100
    assert balance(db, second) == 2050
    assert register(client, "bobby", referral_code=inviter.referral_code).status_code == 400
    assert register(client, "carol", referral_code=user.referral_code).status_code == 201
    assert balance(db, first) == 2100
    entries = db.scalars(select(CreditLedger).where(
        CreditLedger.request_id.in_([f"referral-reward-{second}", f"referral-new-user-{second}"])
    )).all()
    assert len(entries) == 2


def test_self_referral_and_invalid_referral_rejected(client, db):
    uid = register(client).json()["id"]
    code = db.get(User, uid).referral_code
    # Re-registering the same account with its own referral code is rejected as
    # a duplicate account (self-referral farming is disabled at the reward
    # layer: REFERRAL_REWARD_CREDITS=0 in production).
    response = register(client, referral_code=code)
    assert response.status_code == 400
    assert response.json()["detail"] == "邮箱已被注册"
    assert register(client, "bobby", referral_code="missing").status_code == 400
    assert balance(db, uid) == 2000


def test_old_user_login_and_duplicate_register_do_not_grant(client, db):
    from app.core.security import hash_password

    user = User(email="alice@example.com", username="alice", hashed_password=hash_password("secret123"))
    db.add(user)
    db.commit()
    assert register(client).status_code == 400
    assert client.post("/api/auth/login", json={"username": "alice", "password": "secret123"}).status_code == 200
    assert db.scalars(select(CreditLedger)).all() == []


def test_grant_failure_preserves_registration_and_rolls_back_credit(client, db, monkeypatch):
    original = auth.billing_service.grant_credit

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("grant failed after flush")

    monkeypatch.setattr(auth.billing_service, "grant_credit", fail)
    response = register(client)
    assert response.status_code == 201
    assert db.get(User, response.json()["id"]) is not None
    assert db.scalars(select(CreditLedger)).all() == []
    assert client.post("/api/auth/login", json={"username": "alice", "password": "secret123"}).status_code == 200


def test_registration_failure_rolls_back_invite(client, db, monkeypatch):
    monkeypatch.setattr(settings, "INVITE_REQUIRED", True)
    invite = InviteCode(code="BETA", channel="test", max_uses=1)
    db.add(invite)
    db.commit()

    def fail():
        raise IntegrityError("insert", {}, Exception("duplicate"))

    monkeypatch.setattr(db, "commit", fail)
    assert register(client, invite_code="BETA").status_code == 409
    db.refresh(invite)
    assert invite.used_count == 0
    assert db.scalars(select(User)).all() == []


def test_zero_referral_rewards_only_grant_beta(client, db, monkeypatch):
    monkeypatch.setattr(settings, "REFERRAL_REWARD_CREDITS", 0)
    monkeypatch.setattr(settings, "REFERRAL_NEW_USER_CREDITS", 0)
    uid = register(client).json()["id"]
    code = db.get(User, uid).referral_code
    response = register(client, "bobby", referral_code=code)
    assert response.status_code == 201
    assert balance(db, uid) == 2000
    assert balance(db, response.json()["id"]) == 2000
    assert len(db.scalars(select(CreditLedger)).all()) == 2


def test_referral_failure_rolls_back_all_grants_but_keeps_relationship(client, db, monkeypatch):
    uid = register(client).json()["id"]
    code = db.get(User, uid).referral_code
    original = auth.billing_service.grant_credit

    def fail_referral(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get("request_id", "").startswith("referral-new-user-"):
            raise RuntimeError("referral failure after flush")
        return result

    monkeypatch.setattr(auth.billing_service, "grant_credit", fail_referral)
    response = register(client, "bobby", referral_code=code)
    assert response.status_code == 201
    new_user = db.get(User, response.json()["id"])
    assert new_user.referred_by_user_id == uid
    assert balance(db, uid) == 2000
    assert len(db.scalars(select(CreditLedger)).all()) == 1
    monkeypatch.setattr(auth.billing_service, "grant_credit", original)
    auth._grant_registration_credits(db, new_user)
    auth._grant_registration_credits(db, new_user)
    assert balance(db, uid) == 2100
    assert balance(db, new_user.id) == 2050
