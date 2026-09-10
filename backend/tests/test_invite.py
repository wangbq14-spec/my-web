from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.beta import InviteCode
from app.models.user import utcnow_naive
from app.services.invite import validate_and_consume_invite_code


def seed_invite(db, **values):
    invite = InviteCode(code="BETA", channel="test", max_uses=1, **values)
    db.add(invite)
    db.commit()
    return invite


@pytest.mark.parametrize("values,reason", [
    ({"is_active": False}, "邀请码无效"),
    ({"expires_at": utcnow_naive() - timedelta(days=1)}, "邀请码已过期"),
    ({"used_count": 1}, "邀请码已用完"),
])
def test_rejected_invite_does_not_consume(db, values, reason):
    invite = seed_invite(db, **values)
    before = invite.used_count
    with pytest.raises(HTTPException) as exc:
        validate_and_consume_invite_code(db, "BETA")
    assert exc.value.status_code == 400
    assert exc.value.detail == reason
    db.refresh(invite)
    assert invite.used_count == before


def test_missing_invite(db):
    with pytest.raises(HTTPException, match="邀请码无效"):
        validate_and_consume_invite_code(db, "missing")


def test_consumption_obeys_limit_and_caller_rollback(db):
    invite = seed_invite(db)
    assert validate_and_consume_invite_code(db, "BETA").used_count == 1
    with pytest.raises(HTTPException):
        validate_and_consume_invite_code(db, "BETA")
    db.rollback()
    db.refresh(invite)
    assert invite.used_count == 0


def test_atomic_update_rechecks_limit_after_validation(db, monkeypatch):
    invite = seed_invite(db)
    original = db.execute

    def race(statement, *args, **kwargs):
        if getattr(statement, "is_update", False):
            original(update(InviteCode).where(InviteCode.id == invite.id).values(used_count=1))
        return original(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", race)
    with pytest.raises(HTTPException):
        validate_and_consume_invite_code(db, "BETA")
    db.refresh(invite)
    assert invite.used_count == 1


def test_public_preflight_is_read_only(client, db):
    invite = seed_invite(db)
    for _ in range(2):
        assert client.get("/api/invite/validate", params={"code": "BETA"}).json() == {"valid": True}
    db.refresh(invite)
    assert invite.used_count == 0
    assert client.get("/api/invite/validate", params={"code": "missing"}).json() == {
        "valid": False, "reason": "邀请码无效",
    }


def test_concurrent_consumers_cannot_overuse_last_slot(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'invite-race.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            seed_invite(session)
        barrier = Barrier(2)

        def consume():
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    validate_and_consume_invite_code(session, "BETA")
                    session.commit()
                    return 200
                except HTTPException as exc:
                    session.rollback()
                    return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: consume(), range(2)))
        assert sorted(results) == [200, 400]
        with Session(engine) as session:
            assert session.scalar(select(InviteCode.used_count)) == 1
    finally:
        engine.dispose()
