from math import ceil
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.billing import CreditLedger, UsageRecord, UserWallet
from app.models.user import utcnow_naive
from app.llm.base import LLMResponse

class InsufficientCredits(Exception):
    pass

def require_balance(db: Session, user_id: int, minimum: int = 1) -> None:
    balance, _ = get_balance(db, user_id)
    if balance < minimum:
        raise InsufficientCredits()

def charge_response(db: Session, user_id: int, response: LLMResponse, model_tier: str | None = None, description: str = "AI usage", kind: str | None = None) -> UsageRecord | None:
    if response.usage is None:
        return None
    usage = response.usage
    prompt = usage.prompt_tokens or 0
    completion = usage.completion_tokens or 0
    total = usage.total_tokens if usage.total_tokens is not None else prompt + completion
    cost = estimate_cost(prompt, completion, model_tier)
    credits = credits_from_cost(cost)
    request_id = str(uuid4())
    record = record_usage(
        db, user_id, request_id=request_id, provider=response.provider or "unknown",
        model=response.model or "unknown", model_tier=model_tier,
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=total,
        estimated_cost=cost, credits_charged=credits, status="charged", kind=kind,
    )
    if credits:
        consume_credit(db, user_id, credits, request_id, description)
    return record

def create_wallet_if_missing(db: Session, user_id: int) -> UserWallet:
    wallet = db.scalar(select(UserWallet).where(UserWallet.user_id == user_id))
    if wallet is None:
        wallet = UserWallet(user_id=user_id, balance=0); db.add(wallet); db.flush()
    return wallet

def _exists(db, uid, operation, request_id):
    return db.scalar(select(CreditLedger.id).where(CreditLedger.user_id == uid, CreditLedger.operation == operation, CreditLedger.request_id == request_id)) is not None

def grant_credit(db, user_id, amount, description, request_id=None):
    wallet = create_wallet_if_missing(db, user_id)
    if request_id and _exists(db, user_id, "grant", request_id): return wallet
    db.execute(select(UserWallet.user_id).where(UserWallet.user_id == user_id).with_for_update())
    db.execute(update(UserWallet).where(UserWallet.user_id == user_id).values(balance=UserWallet.balance + amount, updated_at=utcnow_naive()))
    db.add(CreditLedger(user_id=user_id, amount=amount, operation="grant", description=description, request_id=request_id)); db.flush(); db.refresh(wallet); return wallet

def consume_credit(db, user_id, amount, request_id, description):
    wallet = create_wallet_if_missing(db, user_id)
    if _exists(db, user_id, "consume", request_id): return wallet
    # Serialize concurrent chargers on the SAME wallet row: every writer first
    # takes the row lock at this single point, so transactions queue instead of
    # deadlocking (MySQL 1213) under concurrent use of one account.
    db.execute(select(UserWallet.user_id).where(UserWallet.user_id == user_id).with_for_update())
    result = db.execute(update(UserWallet).where(UserWallet.user_id == user_id, UserWallet.balance >= amount).values(balance=UserWallet.balance - amount, updated_at=utcnow_naive()))
    if result.rowcount != 1: raise InsufficientCredits()
    db.add(CreditLedger(user_id=user_id, amount=-amount, operation="consume", description=description, request_id=request_id)); db.flush(); db.refresh(wallet); return wallet

def refund_credit(db, user_id, amount, request_id, description):
    wallet = create_wallet_if_missing(db, user_id)
    if _exists(db, user_id, "refund", request_id): return wallet
    db.execute(select(UserWallet.user_id).where(UserWallet.user_id == user_id).with_for_update())
    db.execute(update(UserWallet).where(UserWallet.user_id == user_id).values(balance=UserWallet.balance + amount, updated_at=utcnow_naive()))
    db.add(CreditLedger(user_id=user_id, amount=amount, operation="refund", description=description, request_id=request_id)); db.flush(); db.refresh(wallet); return wallet

def record_usage(db, user_id, **kwargs):
    existing = db.scalar(select(UsageRecord).where(UsageRecord.request_id == kwargs["request_id"], UsageRecord.user_id == user_id))
    if existing: return existing
    record = UsageRecord(user_id=user_id, **kwargs); db.add(record); db.flush(); return record

def get_balance(db, user_id):
    wallet = create_wallet_if_missing(db, user_id); return wallet.balance, wallet.updated_at
def get_usage(db, user_id, limit=20, offset=0):
    return db.scalars(select(UsageRecord).where(UsageRecord.user_id == user_id).order_by(UsageRecord.created_at.desc()).limit(limit).offset(offset)).all()
def _rate_for(tier=None): return settings.CREDIT_INPUT_RATE, settings.CREDIT_OUTPUT_RATE
def estimate_cost(prompt, completion, tier=None):
    in_rate, out_rate = _rate_for(tier); return prompt / 1000 * in_rate + completion / 1000 * out_rate
def credits_from_cost(cost): return max(0, ceil(cost))
