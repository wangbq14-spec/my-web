"""Authenticated feedback submission and listing."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.feedback import FeedbackIn, FeedbackOut
from app.services import feedback

router = APIRouter()


@router.post("", response_model=FeedbackOut, status_code=201)
def submit(payload: FeedbackIn, db: Session = Depends(get_db),
           actor: User = Depends(get_current_user)):
    return feedback.submit_feedback(db, actor.id, **payload.model_dump())


@router.get("", response_model=list[FeedbackOut])
def list_own(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
             db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return feedback.list_own_feedback(db, actor.id, limit, offset)
