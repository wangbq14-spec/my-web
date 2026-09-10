import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.deps import require_admin
from app.models import Feedback, InviteCode, MessageAttachment, RechargeRequest, User
from app.schemas import RechargeRequestIn


def make_user(db, name="beta"):
    user = User(email=f"{name}@example.com", username=name, hashed_password="unused")
    db.add(user)
    db.flush()
    return user


def test_user_beta_defaults_and_referral(db):
    inviter = make_user(db)
    invitee = make_user(db, "invitee")
    assert inviter.role == "user"
    assert inviter.referral_code is None
    assert inviter.referred_by_user_id is None
    inviter.referral_code = "BETA-REF"
    invitee.referred_by_user_id = inviter.id
    db.commit()
    db.refresh(invitee)
    assert invitee.referred_by_user_id == inviter.id
    invitee.referral_code = inviter.referral_code
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_beta_models_create_with_defaults_and_ownership(db):
    user = make_user(db)
    invite = InviteCode(code="BETA", channel="classroom", max_uses=10)
    recharge = RechargeRequest(user_id=user.id, package_code="starter",
                               amount_display="10 CNY", credits_requested=1000)
    feedback = Feedback(user_id=user.id, type="bug", path="/chat", message="Issue")
    attachment = MessageAttachment(user_id=user.id, mime_type="image/png",
                                   original_name="a.png", storage_path="chat/a.png", size_bytes=10)
    db.add_all([invite, recharge, feedback, attachment])
    db.commit()
    assert invite.used_count == 0 and invite.is_active is True
    assert recharge.status == "pending" and recharge.reviewed_at is None
    assert feedback.status == "new"
    assert attachment.type == "image" and attachment.user_id == user.id
    assert attachment.conversation_id is None and attachment.message_id is None
    for record in (invite, recharge, feedback, attachment):
        assert record.id is not None and record.created_at.tzinfo is None


def test_invite_code_is_unique(db):
    db.add(InviteCode(code="SAME", channel="beta", max_uses=1))
    db.commit()
    db.add(InviteCode(code="SAME", channel="beta", max_uses=1))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


@pytest.mark.parametrize("role", ["user", "Admin", "", None])
def test_require_admin_rejects_other_roles(role):
    with pytest.raises(HTTPException) as error:
        require_admin(User(role=role))
    assert error.value.status_code == 403


def test_require_admin_returns_admin():
    user = User(role="admin")
    assert require_admin(user) is user


@pytest.mark.parametrize("changes", [
    {"package_code": " "}, {"package_code": "a" * 41},
    {"amount_display": ""}, {"credits_requested": 0},
    {"credits_requested": -1}, {"credits_requested": True},
    {"credits_requested": 1.5}, {"status": "approved"}, {"user_id": 1},
])
def test_recharge_request_validates_input(changes):
    payload = dict(package_code="starter", amount_display="10 CNY", credits_requested=1000)
    payload.update(changes)
    with pytest.raises(ValidationError):
        RechargeRequestIn(**payload)


def test_recharge_request_accepts_valid_input():
    payload = RechargeRequestIn(package_code="starter", amount_display="10 CNY",
                               credits_requested=1000, note="Paid manually")
    assert payload.credits_requested == 1000
