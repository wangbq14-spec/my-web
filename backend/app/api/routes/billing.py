from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import BalanceOut, UsageOut
from app.services.billing import get_balance, get_usage
router = APIRouter()
@router.get("/balance", response_model=BalanceOut)
def balance(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    value, updated_at = get_balance(db, current_user.id); db.commit(); return {"balance": value, "updated_at": updated_at}
@router.get("/usage", response_model=list[UsageOut])
def usage(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return get_usage(db, current_user.id, limit, offset)
