"""Admin-only Beta analytics endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.services import analytics

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("")
def get_overview(
    range: Literal["7d", "30d", "all"] = "7d",
    db: Session = Depends(get_db),
):
    return analytics.overview(db, range)
