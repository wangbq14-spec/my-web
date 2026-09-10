"""Invite validation and consumption within the caller's transaction."""

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models.beta import InviteCode
from app.models.user import utcnow_naive


def validate_invite_code(db: Session, code: str | None) -> InviteCode:
    invite = db.scalar(select(InviteCode).where(InviteCode.code == (code or "").strip()))
    if invite is None or not invite.is_active:
        raise HTTPException(status_code=400, detail="邀请码无效")
    if invite.expires_at is not None and invite.expires_at <= utcnow_naive():
        raise HTTPException(status_code=400, detail="邀请码已过期")
    if invite.used_count >= invite.max_uses:
        raise HTTPException(status_code=400, detail="邀请码已用完")
    return invite


def validate_and_consume_invite_code(db: Session, code: str) -> InviteCode:
    invite = validate_invite_code(db, code)
    result = db.execute(
        update(InviteCode).where(
            InviteCode.id == invite.id,
            InviteCode.used_count < InviteCode.max_uses,
            InviteCode.is_active.is_(True),
            or_(InviteCode.expires_at.is_(None), InviteCode.expires_at > utcnow_naive()),
        ).values(used_count=InviteCode.used_count + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.refresh(invite)
        validate_invite_code(db, code)
        raise HTTPException(status_code=400, detail="邀请码无效，请重试")
    db.refresh(invite)
    return invite
