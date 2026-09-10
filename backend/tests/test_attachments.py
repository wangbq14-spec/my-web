import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from sqlalchemy import select

from app.api.routes.auth import get_current_user
from app.core.config import settings
from app.main import app
from app.models.beta import MessageAttachment
from app.models.user import User
from app.services.attachments import (
    attachment_path, sanitize_filename, upload_attachment, validate_attachments,
)

IMAGES = [
    ("photo.jpg", "image/jpeg", b"\xff\xd8\xff\xe0test"),
    ("photo.png", "image/png", b"\x89PNG\r\n\x1a\ntest"),
    ("photo.webp", "image/webp", b"RIFF\x10\x00\x00\x00WEBPtest"),
]


@pytest.fixture
def owner(db):
    user = User(email="images@example.com", username="images", hashed_password="x")
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def auth_client(client, owner):
    app.dependency_overrides[get_current_user] = lambda: owner
    yield client
    app.dependency_overrides.pop(get_current_user, None)


def upload(db, owner, name="photo.png", mime="image/png", raw=IMAGES[1][2]):
    file = UploadFile(filename=name, file=BytesIO(raw), headers=Headers({"content-type": mime}))
    return asyncio.run(upload_attachment(db, owner.id, file))


@pytest.mark.parametrize("name,mime,raw", IMAGES)
def test_upload_and_private_download(auth_client, db, owner, name, mime, raw):
    response = auth_client.post("/api/chat/attachments", files={"file": (name, raw, mime)})
    assert response.status_code == 201, response.text
    data = response.json()
    assert set(data) == {"id", "type", "mime_type", "original_name", "url", "size_bytes", "created_at"}
    assert data["size_bytes"] == len(raw)
    row = db.get(MessageAttachment, data["id"])
    path = attachment_path(row, owner.id)
    assert path.read_bytes() == raw
    assert path.name != name
    assert path.parent == Path(settings.RAG_UPLOAD_DIR) / "chat_attachments" / str(owner.id)
    response = auth_client.get(data["url"])
    assert response.status_code == 200
    assert response.content == raw
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("name,mime,raw", [
    ("a.gif", "image/gif", b"GIF89a"), ("a.txt", "text/plain", b"hello"),
    ("a.jpg", "image/png", IMAGES[0][2]), ("a.png", "image/png", b"not an image"),
    ("a.webp", "image/webp", b"RIFF0000NOPE"), ("a.jpg", "image/jpeg", b""),
])
def test_upload_rejects_invalid_image(auth_client, db, name, mime, raw):
    assert auth_client.post("/api/chat/attachments", files={"file": (name, raw, mime)}).status_code == 415
    assert db.scalars(select(MessageAttachment)).all() == []


def test_upload_size_limit(auth_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CHAT_IMAGE_SIZE", 8)
    assert auth_client.post("/api/chat/attachments", files={
        "file": ("a.png", IMAGES[1][2], "image/png")}).status_code == 413


def test_upload_requires_authentication(client):
    assert client.post("/api/chat/attachments", files={
        "file": ("a.png", IMAGES[1][2], "image/png")}).status_code == 401


@pytest.mark.parametrize("name", ["../a.png", r"..\a.png", "/tmp/a.png",
                                  r"C:\tmp\a.png", "dir/../a.png", r"\\host\a.png"])
def test_path_traversal_rejected(name):
    with pytest.raises(HTTPException) as error:
        sanitize_filename(name)
    assert error.value.status_code == 400


def test_filename_sanitized():
    assert sanitize_filename("folder/hello<>?.png") == ("hello___.png", ".png")


def test_ownership(db, owner):
    row = upload(db, owner)
    with pytest.raises(HTTPException) as error:
        validate_attachments(db, owner.id + 1, 1, [row.id])
    assert error.value.status_code == 404


def test_download_ownership(auth_client, db, owner):
    row = upload(db, owner)
    db.commit()
    other = User(email="other@example.com", username="other", hashed_password="x")
    db.add(other)
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: other
    assert auth_client.get(f"/api/chat/attachments/{row.id}").status_code == 404


def test_storage_path_revalidated(db, owner, tmp_path):
    row = upload(db, owner)
    row.storage_path = str(tmp_path / "outside.png")
    with pytest.raises(HTTPException):
        attachment_path(row, owner.id)


def test_duplicate_and_count_limit(db, owner):
    row = upload(db, owner)
    for ids in ([row.id, row.id], [1, 2, 3, 4, 5]):
        with pytest.raises(HTTPException) as error:
            validate_attachments(db, owner.id, 1, ids)
        assert error.value.status_code == 400


def test_upload_uses_general_rate_limit(auth_client, monkeypatch):
    from app.middleware.rate_limit import RateLimitMiddleware
    RateLimitMiddleware.reset_all()
    monkeypatch.setattr(settings, "RATE_LIMIT_GENERAL", 1)
    first = auth_client.post("/api/chat/attachments", files={
        "file": ("a.png", IMAGES[1][2], "image/png")})
    assert first.status_code == 201
    assert auth_client.post("/api/chat/attachments", files={
        "file": ("a.png", IMAGES[1][2], "image/png")}).status_code == 429