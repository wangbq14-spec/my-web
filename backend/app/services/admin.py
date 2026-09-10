"""Administrative operations. Mutations own commit/rollback for the request session."""

import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
import secrets

from fastapi import HTTPException
from sqlalchemy import func, or_, select, union, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import RECHARGE_PACKAGES, settings
from app.models.beta import InviteCode, RechargeRequest
from app.models.billing import CreditLedger, UsageRecord, UserWallet
from app.models.conversation import Conversation
from app.models.project import Project
from app.models.user import User, utcnow_naive
from app.services import billing


@contextmanager
def transaction(db: Session):
    try:
        yield
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Conflicting operation") from exc
    except Exception:
        db.rollback()
        raise


def user_query():
    usage = select(
        UsageRecord.user_id,
        func.count(UsageRecord.id).label("usage_count"),
        func.sum(UsageRecord.credits_charged).label("credits_charged"),
    ).group_by(UsageRecord.user_id).subquery()
    activity = union(
        select(UsageRecord.user_id.label("user_id"), UsageRecord.created_at.label("ts")),
        select(Conversation.user_id.label("user_id"), Conversation.updated_at.label("ts")),
        select(Project.user_id.label("user_id"), Project.last_activity_at.label("ts")),
    ).subquery()
    last_active = select(
        activity.c.user_id, func.max(activity.c.ts).label("last_active_at")
    ).group_by(activity.c.user_id).subquery()
    return select(
        User.id, User.username, User.email, User.role, User.is_active, User.created_at,
        func.coalesce(UserWallet.balance, 0).label("balance"),
        func.coalesce(usage.c.usage_count, 0).label("usage_count"),
        func.coalesce(usage.c.credits_charged, 0).label("credits_charged"),
        last_active.c.last_active_at,
    ).outerjoin(UserWallet, UserWallet.user_id == User.id).outerjoin(
        usage, usage.c.user_id == User.id
    ).outerjoin(last_active, last_active.c.user_id == User.id)


# Minimal user-list filters for the Beta operations center.
_USER_FILTERS = ("active", "new", "low_balance")
_LOW_BALANCE_THRESHOLD = 100


def list_users(db, search=None, limit=20, offset=0, filter=None):
    statement = user_query()
    if search:
        statement = statement.where(or_(
            User.username.contains(search, autoescape=True),
            User.email.contains(search, autoescape=True),
        ))
    if filter == "active":
        statement = statement.where(User.is_active.is_(True))
    elif filter == "new":
        today_start = datetime.now(timezone.utc).replace(tzinfo=None).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        statement = statement.where(User.created_at >= today_start)
    elif filter == "low_balance":
        statement = statement.where(
            func.coalesce(UserWallet.balance, 0) < _LOW_BALANCE_THRESHOLD
        )
    return [dict(row) for row in db.execute(
        statement.order_by(User.id).limit(limit).offset(offset)
    ).mappings()]


def get_user(db, user_id):
    row = db.execute(user_query().where(User.id == user_id)).mappings().first()
    if row is None:
        raise HTTPException(404, "User not found")
    return dict(row)


def grant_credits(db, user_id, admin_id, amount, reason, request_id=None):
    description = f"admin:{admin_id}: {reason}"
    with transaction(db):
        if db.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
            raise HTTPException(404, "User not found")
        # Recharge approval keys are reserved for the server.
        if request_id and request_id.startswith("recharge-approve-"):
            raise HTTPException(409, "Reserved request_id")
        existing = None
        if request_id:
            existing = db.scalar(select(CreditLedger).where(
                CreditLedger.request_id == request_id, CreditLedger.operation == "grant"
            ))
        if existing and (
            existing.user_id != user_id or existing.amount != amount
            or existing.description != description
        ):
            raise HTTPException(409, "request_id was used with different grant details")
        wallet = billing.grant_credit(db, user_id, amount, description, request_id)
        result = {"balance": wallet.balance, "updated_at": wallet.updated_at}
    return result


def list_invite_codes(db, limit=20, offset=0):
    return db.scalars(select(InviteCode).order_by(
        InviteCode.id.desc()
    ).limit(limit).offset(offset)).all()


def create_invite_code(db, admin_id, channel, max_uses, expires_at=None):
    if expires_at is not None and expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    with transaction(db):
        invite = InviteCode(
            code=f"OMNIXA-AI-{secrets.token_hex(16).upper()}",
            channel=channel, max_uses=max_uses, expires_at=expires_at,
            created_by=admin_id,
        )
        db.add(invite)
        db.flush()
    return invite


def disable_invite_code(db, invite_id):
    with transaction(db):
        invite = db.get(InviteCode, invite_id)
        if invite is None:
            raise HTTPException(404, "Invite code not found")
        invite.is_active = False
    return invite


def quote_custom(amount_cny: Decimal) -> dict:
    """Server-side pricing for a custom recharge amount. Never trusts the client."""
    if not settings.CUSTOM_RECHARGE_ENABLED:
        raise HTTPException(403, "Custom recharge is disabled")
    if not amount_cny.is_finite() or amount_cny <= 0:
        raise HTTPException(422, "Invalid amount")
    if amount_cny < settings.CUSTOM_RECHARGE_MIN_CNY or amount_cny > settings.CUSTOM_RECHARGE_MAX_CNY:
        raise HTTPException(422, "Invalid amount")
    step = settings.CUSTOM_RECHARGE_STEP_CNY
    if step > 0 and (amount_cny - settings.CUSTOM_RECHARGE_MIN_CNY) % step != 0:
        raise HTTPException(422, "Invalid amount")
    credits = int((amount_cny * settings.CREDIT_PER_CNY).to_integral_value(rounding=ROUND_HALF_UP))
    return {
        "amount_cny": str(amount_cny),
        "credits": credits,
        "pricing_version": settings.RECHARGE_PRICING_VERSION,
        "expires_at": (utcnow_naive() + timedelta(minutes=15)).isoformat(),
    }


def submit_recharge(db, user_id, package_code=None, credits_requested=None, note=None, amount_cny=None):
    if amount_cny is not None:
        if package_code is not None:
            raise HTTPException(422, "Provide package_code or amount_cny, not both")
        quote = quote_custom(amount_cny)
        if credits_requested is not None and credits_requested != quote["credits"]:
            raise HTTPException(422, "credits_requested does not match server pricing")
        snapshot = json.dumps({
            "pricing_version": settings.RECHARGE_PRICING_VERSION,
            "rate_per_cny": str(settings.CREDIT_PER_CNY),
            "amount_cny": str(amount_cny),
            "credits": quote["credits"],
        }, ensure_ascii=False)
        with transaction(db):
            request = RechargeRequest(
                user_id=user_id, package_code="custom",
                amount_display=f"{amount_cny} CNY",
                amount_cny=amount_cny,
                credits_requested=quote["credits"],
                pricing_snapshot=snapshot, note=note,
            )
            db.add(request)
            db.flush()
        return request

    if package_code is None:
        raise HTTPException(422, "Provide package_code or amount_cny")
    package = RECHARGE_PACKAGES.get(package_code)
    if package is None or credits_requested != package["credits"]:
        raise HTTPException(422, "Unknown package or incorrect credits_requested")
    with transaction(db):
        request = RechargeRequest(
            user_id=user_id, package_code=package_code,
            credits_requested=package["credits"],
            amount_display=package["amount_display"], note=note,
        )
        db.add(request)
        db.flush()
    return request


def list_recharges(db, user_id=None, status=None, limit=20, offset=0):
    statement = select(RechargeRequest, User.username).join(
        User, User.id == RechargeRequest.user_id
    )
    if user_id is not None:
        statement = statement.where(RechargeRequest.user_id == user_id)
    if status is not None:
        statement = statement.where(RechargeRequest.status == status)
    rows = db.execute(
        statement.order_by(RechargeRequest.id.desc()).limit(limit).offset(offset)
    ).all()
    result = []
    for request, username in rows:
        item = {c.name: getattr(request, c.name) for c in RechargeRequest.__table__.columns}
        item["username"] = username
        result.append(item)
    return result


def transition_recharge(db, request_id, status, admin_id=None, user_id=None, note=None):
    with transaction(db):
        statement = update(RechargeRequest).where(
            RechargeRequest.id == request_id, RechargeRequest.status == "pending"
        )
        if user_id is not None:
            statement = statement.where(RechargeRequest.user_id == user_id)
        values = {"status": status}
        if admin_id is not None:
            values.update(reviewed_by=admin_id, reviewed_at=utcnow_naive())
        result = db.execute(statement.values(**values))
        if result.rowcount != 1:
            raise HTTPException(409, "Request is unavailable or no longer pending")
        request = db.get(RechargeRequest, request_id)
        db.refresh(request)
        if note:
            request.note = "\n".join(filter(None, [
                request.note, f"admin:{admin_id}: {note}"
            ]))
        if status == "approved":
            # Serialize wallet creation with other admin grants for this user.
            db.execute(select(User.id).where(
                User.id == request.user_id
            ).with_for_update())
            billing.grant_credit(
                db, request.user_id, request.credits_requested,
                f"admin:{admin_id}: approve recharge {request_id} ({request.package_code})",
                request_id=f"recharge-approve-{request_id}",
            )
        db.flush()
    return request
