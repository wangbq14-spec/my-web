"""Tests for the secure admin bootstrap script (data/maintenance/create_admin.py).

Verifies the role is written explicitly (never inferred from the username) and
that the password is hashed with the same scheme the auth flow verifies.
"""
import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.models.user import User

SCRIPT = Path(__file__).resolve().parents[1] / "data" / "maintenance" / "create_admin.py"


def _load():
    spec = importlib.util.spec_from_file_location("omnixa_create_admin", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["omnixa_create_admin"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def create_admin(db, monkeypatch):
    mod = _load()

    @contextmanager
    def fake_session():
        yield db

    monkeypatch.setattr(mod, "SessionLocal", lambda: fake_session())
    return mod


def test_creates_admin_with_hashed_password(create_admin, db):
    rc = create_admin.main(
        ["--email", "admin@example.com", "--username", "boss",
         "--password", "long-password-123"]
    )
    assert rc == 0
    user = db.scalars(select(User).where(User.email == "admin@example.com")).first()
    assert user is not None
    assert user.role == "admin"
    assert user.username == "boss"
    assert verify_password("long-password-123", user.hashed_password)


def test_promotes_existing_user_to_admin(create_admin, db):
    user = User(email="x@example.com", username="x", hashed_password="old", role="user")
    db.add(user)
    db.commit()
    rc = create_admin.main(
        ["--email", "x@example.com", "--username", "x",
         "--password", "long-password-456"]
    )
    assert rc == 0
    db.refresh(user)
    assert user.role == "admin"
    assert verify_password("long-password-456", user.hashed_password)


def test_rejects_short_password(create_admin):
    with pytest.raises(SystemExit):
        create_admin.main(
            ["--email", "a@example.com", "--username", "a",
             "--password", "short"]
        )


def test_rejects_username_clash(create_admin, db):
    db.add(User(email="a@example.com", username="taken", hashed_password="x", role="user"))
    db.commit()
    with pytest.raises(SystemExit):
        create_admin.main(
            ["--email", "b@example.com", "--username", "taken",
             "--password", "long-password-789"]
        )
