from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.billing import CreditLedger, UsageRecord, UserWallet
from app.models.user import User
from app.services.billing import (
    InsufficientCredits,
    consume_credit,
    credits_from_cost,
    estimate_cost,
    get_balance,
    get_usage,
    grant_credit,
    record_usage,
    refund_credit,
)


def make_user(db, name="alice"):
    user = User(email=f"{name}@example.com", username=name, hashed_password="x")
    db.add(user)
    db.flush()
    return user.id


def test_wallet_operations_are_balanced_and_idempotent(db):
    user_id = make_user(db)
    grant_credit(db, user_id, 100, "test", "grant-1")
    grant_credit(db, user_id, 100, "test", "grant-1")
    consume_credit(db, user_id, 30, "consume-1", "test")
    consume_credit(db, user_id, 30, "consume-1", "test")
    refund_credit(db, user_id, 10, "refund-1", "test")
    refund_credit(db, user_id, 10, "refund-1", "test")
    db.commit()

    balance, _ = get_balance(db, user_id)
    assert balance == 80
    rows = db.scalars(select(CreditLedger).where(CreditLedger.user_id == user_id)).all()
    assert len(rows) == 3
    assert sorted(row.operation for row in rows) == ["consume", "grant", "refund"]


def test_consume_never_makes_balance_negative(db):
    user_id = make_user(db)
    grant_credit(db, user_id, 10, "test", "grant")
    db.commit()
    with pytest.raises(InsufficientCredits):
        consume_credit(db, user_id, 11, "consume", "test")
    db.rollback()
    assert get_balance(db, user_id)[0] == 10


def test_lazy_wallet_and_usage_idempotency_and_ownership(db):
    alice, bob = make_user(db, "alice"), make_user(db, "bob")
    assert get_balance(db, alice)[0] == 0
    kwargs = dict(request_id="usage-1", provider="fake", model="m", model_tier=None,
                  prompt_tokens=1, completion_tokens=2, total_tokens=3,
                  estimated_cost=0.0, credits_charged=0, status="charged")
    record_usage(db, alice, **kwargs)
    record_usage(db, alice, **kwargs)
    db.commit()
    assert len(get_usage(db, alice)) == 1
    assert get_usage(db, bob) == []
    assert get_balance(db, bob)[0] == 0


def test_pricing_zero_and_boundaries():
    assert estimate_cost(0, 0) == 0
    assert credits_from_cost(0) == 0
    assert credits_from_cost(0.01) == 1


def test_concurrent_conditional_consumption_cannot_overdraw(tmp_path):
    db_path = tmp_path / "billing-concurrency.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(engine)
    setup = Session(engine)
    user_id = make_user(setup)
    grant_credit(setup, user_id, 20, "test", "grant")
    setup.commit()
    setup.close()

    def consume(i):
        local = Session(engine)
        try:
            consume_credit(local, user_id, 3, f"parallel-{i}", "test")
            local.commit()
            return True
        except InsufficientCredits:
            local.rollback()
            return False
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(consume, range(8)))
    verify = Session(engine)
    try:
        verify.expire_all()
        assert get_balance(verify, user_id)[0] >= 0
        assert sum(results) * 3 <= 20
        consume_rows = verify.scalars(
            select(CreditLedger).where(
                CreditLedger.user_id == user_id,
                CreditLedger.operation == "consume",
            )
        ).all()
        assert len(consume_rows) == sum(results)
    finally:
        verify.close()
        engine.dispose()
