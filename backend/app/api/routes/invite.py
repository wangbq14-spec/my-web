"""Public read-only invite preflight."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.invite import validate_invite_code

router = APIRouter()


@router.get("/validate")
def validate(code: str, db: Session = Depends(get_db)) -> dict:
    try:
        validate_invite_code(db, code)
    except HTTPException as exc:
        if exc.status_code != 400:
            raise
        return {"valid": False, "reason": exc.detail}
    return {"valid": True}
