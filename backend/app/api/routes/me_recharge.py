"""Authenticated recharge requests; pricing is resolved exclusively by the server."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.config import RECHARGE_PACKAGES, settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.recharge import RechargeRequestOut
from app.services import admin

router = APIRouter()


class RechargeSubmitIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    package_code: str | None = Field(default=None, min_length=1, max_length=40)
    credits_requested: int | None = Field(default=None, strict=True, gt=0, le=2147483647)
    amount_cny: Decimal | None = None
    note: str | None = Field(default=None, max_length=10000)


class RechargeQuoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_cny: Decimal


@router.get("/payment-info")
def payment_info(actor: User = Depends(get_current_user)):
    packages = [
        {"code": code, "credits": pkg["credits"], "amount_display": pkg["amount_display"]}
        for code, pkg in sorted(RECHARGE_PACKAGES.items(), key=lambda kv: kv[1]["credits"])
    ]
    qr = settings.PAYMENT_QR_IMAGE_URL or None
    custom_recharge = {
        "enabled": settings.CUSTOM_RECHARGE_ENABLED,
        "min_cny": str(settings.CUSTOM_RECHARGE_MIN_CNY),
        "max_cny": str(settings.CUSTOM_RECHARGE_MAX_CNY),
        "step_cny": str(settings.CUSTOM_RECHARGE_STEP_CNY),
        "credit_per_cny": str(settings.CREDIT_PER_CNY),
        "pricing_version": settings.RECHARGE_PRICING_VERSION,
    }
    return {"qr_image_url": qr, "packages": packages, "custom_recharge": custom_recharge}


@router.post("/recharge-quote")
def recharge_quote(payload: RechargeQuoteIn, actor: User = Depends(get_current_user)):
    return admin.quote_custom(payload.amount_cny)


@router.post("/recharge-requests", response_model=RechargeRequestOut, status_code=201)
def submit(payload: RechargeSubmitIn, db: Session = Depends(get_db),
           actor: User = Depends(get_current_user)):
    return admin.submit_recharge(db, actor.id, **payload.model_dump())


@router.get("/recharge-requests", response_model=list[RechargeRequestOut])
def requests(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
             db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    return admin.list_recharges(db, user_id=actor.id, limit=limit, offset=offset)


@router.post("/recharge-requests/{request_id}/cancel", response_model=RechargeRequestOut)
def cancel(request_id: int, db: Session = Depends(get_db),
           actor: User = Depends(get_current_user)):
    return admin.transition_recharge(db, request_id, "cancelled", user_id=actor.id)
