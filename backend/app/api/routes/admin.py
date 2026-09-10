"""Admin-only user, invite, and recharge management endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.billing import CreditLedger
from app.models.user import User
from app.schemas.billing import UsageOut
from app.schemas.feedback import FeedbackOut
from app.schemas.invite import InviteCodeOut
from app.schemas.recharge import RechargeRequestOut
from app.services import admin, analytics, attachments, billing, feedback

router = APIRouter(dependencies=[Depends(require_admin)])


def _ensure_user(db: Session, user_id: int) -> None:
    if db.scalar(select(User.id).where(User.id == user_id)) is None:
        raise HTTPException(404, "User not found")


class OrphanCleanupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before_hours: int = Field(default=24, ge=1, le=720)


class GrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    amount: int = Field(strict=True, gt=0, le=2147483647)
    reason: str = Field(min_length=1, max_length=10000)
    request_id: str | None = Field(default=None, min_length=1, max_length=64)


class InviteCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    channel: str = Field(min_length=1, max_length=40)
    max_uses: int = Field(strict=True, gt=0, le=2147483647)
    expires_at: datetime | None = None


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str | None = Field(default=None, max_length=10000)


class FeedbackStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["reviewed", "closed"]


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """Operations overview for the admin home (today + 7d + beta health)."""
    return analytics.admin_overview(db)


@router.post("/attachments/cleanup-orphans")
def cleanup_orphans(payload: OrphanCleanupIn, db: Session = Depends(get_db)):
    """Maintenance: remove image attachments unbound to any message and older
    than ``before_hours`` (abandoned uploads / leftovers of deleted items)."""
    before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        hours=payload.before_hours
    )
    removed = attachments.cleanup_orphan_attachments(db, before)
    db.commit()
    return {"removed": removed}


@router.get("/users")
def users(search: str | None = Query(None, max_length=191),
          filter: Literal["active", "new", "low_balance"] | None = None,
          limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
          db: Session = Depends(get_db)):
    return admin.list_users(db, search, limit, offset, filter=filter)


@router.get("/users/{user_id}")
def user_detail(user_id: int, db: Session = Depends(get_db)):
    return admin.get_user(db, user_id)


@router.get("/users/{user_id}/usage", response_model=list[UsageOut])
def user_usage(user_id: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db)):
    _ensure_user(db, user_id)
    return billing.get_usage(db, user_id, limit, offset)


@router.get("/users/{user_id}/ledger")
def user_ledger(user_id: int, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db)):
    _ensure_user(db, user_id)
    rows = db.scalars(
        select(CreditLedger).where(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.id.desc()).limit(limit).offset(offset)
    ).all()
    return [
        {"id": r.id, "user_id": r.user_id, "amount": r.amount, "operation": r.operation,
         "description": r.description, "request_id": r.request_id, "created_at": r.created_at}
        for r in rows
    ]


@router.get("/users/{user_id}/feedback", response_model=list[FeedbackOut])
def user_feedback(user_id: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                  db: Session = Depends(get_db)):
    _ensure_user(db, user_id)
    return feedback.list_own_feedback(db, user_id, limit, offset)


@router.get("/users/{user_id}/recharge-requests", response_model=list[RechargeRequestOut])
def user_recharges(user_id: int, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                   db: Session = Depends(get_db)):
    _ensure_user(db, user_id)
    return admin.list_recharges(db, user_id=user_id, limit=limit, offset=offset)


@router.post("/users/{user_id}/grant-credits")
def grant(user_id: int, payload: GrantIn, db: Session = Depends(get_db),
          actor: User = Depends(require_admin)):
    return admin.grant_credits(db, user_id, actor.id, **payload.model_dump())


@router.get("/invite-codes", response_model=list[InviteCodeOut])
def invite_codes(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db)):
    return admin.list_invite_codes(db, limit, offset)


@router.post("/invite-codes", response_model=InviteCodeOut, status_code=201)
def create_invite(payload: InviteCreateIn, db: Session = Depends(get_db),
                  actor: User = Depends(require_admin)):
    return admin.create_invite_code(db, actor.id, **payload.model_dump())


@router.post("/invite-codes/{invite_id}/disable", response_model=InviteCodeOut)
def disable_invite(invite_id: int, db: Session = Depends(get_db)):
    return admin.disable_invite_code(db, invite_id)


@router.get("/recharge-requests", response_model=list[RechargeRequestOut])
def recharge_requests(
    status: Literal["pending", "approved", "rejected", "cancelled"] | None = None,
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return admin.list_recharges(db, status=status, limit=limit, offset=offset)


@router.post("/recharge-requests/{request_id}/approve", response_model=RechargeRequestOut)
def approve(request_id: int, payload: ReviewIn | None = None,
            db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    return admin.transition_recharge(
        db, request_id, "approved", admin_id=actor.id,
        note=payload.note if payload else None,
    )


@router.post("/recharge-requests/{request_id}/reject", response_model=RechargeRequestOut)
def reject(request_id: int, payload: ReviewIn | None = None,
           db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    return admin.transition_recharge(
        db, request_id, "rejected", admin_id=actor.id,
        note=payload.note if payload else None,
    )


@router.get("/feedback", response_model=list[FeedbackOut])
def feedback_list(
    status: Literal["new", "reviewed", "closed"] | None = None,
    type: Literal["bug", "suggestion", "other"] | None = None,
    limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return feedback.list_feedback(db, status=status, type=type, limit=limit, offset=offset)


@router.post("/feedback/{feedback_id}/status", response_model=FeedbackOut)
def feedback_status(feedback_id: int, payload: FeedbackStatusIn,
                    db: Session = Depends(get_db)):
    return feedback.update_feedback_status(db, feedback_id, payload.status)
