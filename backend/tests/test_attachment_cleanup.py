"""Attachment orphan cleanup foundation (Wave C: image lifecycle)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.beta import MessageAttachment
from app.models.user import User, utcnow_naive
from app.services import attachments


@pytest.fixture()
def actors(db):
    users = [User(username=name, email=f"{name}@example.com", hashed_password="unused",
                  role=role) for name, role in [("admin", "admin"), ("alice", "user")]]
    db.add_all(users)
    db.commit()
    return [(u.id, {"Authorization": f"Bearer {create_access_token(subject=str(u.id))}"}) for u in users]


def _attachment(db, user_id, *, message_id=None, conversation_id=None, age_hours=48, storage="unused.png"):
    row = MessageAttachment(
        user_id=user_id, type="image", mime_type="image/png",
        original_name="old.png", storage_path=storage, size_bytes=10,
        created_at=utcnow_naive() - timedelta(hours=age_hours),
    )
    if message_id is not None:
        row.message_id = message_id
    if conversation_id is not None:
        row.conversation_id = conversation_id
    db.add(row)
    return row


def test_cleanup_removes_only_unbound_and_old_rows(db, actors, tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.RAG_UPLOAD_DIR", str(tmp_path))
    alice_id = actors[1][0]
    orphan_file = tmp_path / "orphan.png"
    orphan_file.write_bytes(b"\x89PNG\r\n\x1a\n")
    orphan = _attachment(db, alice_id, age_hours=72, storage=str(orphan_file))
    recent_unbound = _attachment(db, alice_id, age_hours=2, storage="recent.png")
    bound = _attachment(db, alice_id, message_id=99, age_hours=72, storage="bound.png")
    db.add_all([orphan, recent_unbound, bound])
    db.commit()

    before = utcnow_naive() - timedelta(hours=24)
    removed = attachments.cleanup_orphan_attachments(db, before)
    db.commit()

    assert removed == 1
    remaining = {row.id: row for row in db.scalars(select(MessageAttachment)).all()}
    assert orphan.id not in remaining
    assert recent_unbound.id in remaining  # too recent -> keep (in-flight upload)
    assert bound.id in remaining  # bound to a message -> keep
    assert not orphan_file.exists()  # file removed with the row


def test_cleanup_never_touches_files_outside_upload_root(db, actors, tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.RAG_UPLOAD_DIR", str(tmp_path))
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes(b"data")
    row = _attachment(db, actors[1][0], age_hours=72, storage=str(outside))
    db.add(row)
    db.commit()

    before = utcnow_naive() - timedelta(hours=24)
    removed = attachments.cleanup_orphan_attachments(db, before)
    db.commit()
    assert removed == 1
    assert outside.exists()  # row removed, external file untouched


def test_cleanup_orphans_endpoint_requires_admin(client, db, actors):
    assert client.post("/api/admin/attachments/cleanup-orphans",
                       headers=actors[1][1], json={}).status_code == 403


def test_cleanup_orphans_endpoint_removes_rows(client, db, actors, tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.RAG_UPLOAD_DIR", str(tmp_path))
    orphan = _attachment(db, actors[1][0], age_hours=72)
    db.add(orphan)
    db.commit()

    response = client.post("/api/admin/attachments/cleanup-orphans",
                           headers=actors[0][1], json={"before_hours": 24})
    assert response.status_code == 200
    assert response.json()["removed"] == 1
    assert db.scalar(select(MessageAttachment.id).where(MessageAttachment.id == orphan.id)) is None
