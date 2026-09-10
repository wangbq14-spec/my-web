"""Feedback operations. Mutations own commit/rollback for the request session."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.beta import Feedback
from app.models.user import User
from app.services.admin import transaction

_FEEDBACK_TRANSITIONS = {"reviewed", "closed"}


def submit_feedback(db: Session, user_id: int, type: str, path: str, message: str) -> Feedback:
    with transaction(db):
        feedback = Feedback(user_id=user_id, type=type, path=path, message=message, status="new")
        db.add(feedback)
        db.flush()
    return feedback


def list_own_feedback(db: Session, user_id: int, limit: int, offset: int) -> list[Feedback]:
    return db.scalars(
        select(Feedback)
        .where(Feedback.user_id == user_id)
        .order_by(Feedback.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()


def list_feedback(db: Session, status=None, type=None, limit: int = 20, offset: int = 0) -> list[dict]:
    statement = select(Feedback, User.username).join(User, User.id == Feedback.user_id)
    if status is not None:
        statement = statement.where(Feedback.status == status)
    if type is not None:
        statement = statement.where(Feedback.type == type)
    rows = db.execute(
        statement.order_by(Feedback.id.desc()).limit(limit).offset(offset)
    ).all()
    result = []
    for feedback, username in rows:
        item = {c.name: getattr(feedback, c.name) for c in Feedback.__table__.columns}
        item["username"] = username
        result.append(item)
    return result


def update_feedback_status(db: Session, feedback_id: int, status: str) -> Feedback:
    if status not in _FEEDBACK_TRANSITIONS:
        raise HTTPException(422, "Invalid feedback status")
    with transaction(db):
        feedback = db.get(Feedback, feedback_id)
        if feedback is None:
            raise HTTPException(404, "Feedback not found")
        feedback.status = status
    return feedback
