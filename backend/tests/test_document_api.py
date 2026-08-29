from pathlib import Path

import pytest

from app.core.config import settings
from app.models.document import Document
from app.rag.storage import StorageSecurityError, resolve_upload_path


def _register_and_login(client, username: str) -> str:
    client.post(
        "/api/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "secret123",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _upload(client, token: str, filename: str, content: bytes):
    return client.post(
        "/api/documents",
        files={"file": (filename, content, "application/octet-stream")},
        headers=_auth(token),
    )


def test_upload_txt_and_md_success(client):
    token = _register_and_login(client, "alice")

    txt = _upload(client, token, "notes.txt", b"hello")
    markdown = _upload(client, token, "notes.md", b"# heading")

    assert txt.status_code == 201
    assert markdown.status_code == 201
    assert txt.json()["original_filename"] == "notes.txt"
    assert txt.json()["filename"].endswith(".txt")
    assert txt.json()["content_type"] == "text/plain"
    assert markdown.json()["content_type"] == "text/markdown"
    assert "user_id" not in txt.json()


def test_upload_rejects_unsupported_extension(client):
    token = _register_and_login(client, "alice")

    response = _upload(client, token, "malware.exe", b"not executable")

    assert response.status_code == 422
    assert response.json()["detail"] == "不支持的文件类型"


def test_upload_rejects_empty_file(client):
    token = _register_and_login(client, "alice")

    response = _upload(client, token, "empty.txt", b"")

    assert response.status_code == 422
    assert response.json()["detail"] == "文件为空"


def test_upload_rejects_too_large_file(client, monkeypatch):
    token = _register_and_login(client, "alice")
    monkeypatch.setattr(settings, "RAG_MAX_UPLOAD_BYTES", 3)

    response = _upload(client, token, "large.txt", b"1234")

    assert response.status_code == 413
    assert response.json()["detail"] == "文件过大"


def test_upload_uses_internal_safe_filename(client):
    token = _register_and_login(client, "alice")

    response = _upload(client, token, "../../outside.txt", b"safe")

    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "../../outside.txt"
    assert Path(data["filename"]).name == data["filename"]
    assert resolve_upload_path(data["filename"]).is_file()
    assert not (Path(settings.RAG_UPLOAD_DIR).parent / "outside.txt").exists()


def test_resolve_upload_path_rejects_path_traversal():
    with pytest.raises(StorageSecurityError):
        resolve_upload_path("../outside.txt")


def test_upload_requires_authentication(client):
    response = client.post(
        "/api/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 401


def test_list_only_contains_current_users_documents(client):
    alice = _register_and_login(client, "alice")
    bob = _register_and_login(client, "bob")
    _upload(client, alice, "alice.txt", b"alice")
    _upload(client, bob, "bob.txt", b"bob")

    response = client.get("/api/documents", headers=_auth(alice))

    assert response.status_code == 200
    assert [item["original_filename"] for item in response.json()] == ["alice.txt"]


def test_get_and_delete_other_users_document_return_404(client):
    alice = _register_and_login(client, "alice")
    bob = _register_and_login(client, "bob")
    created = _upload(client, bob, "bob.txt", b"bob").json()

    assert client.get(f"/api/documents/{created['id']}", headers=_auth(alice)).status_code == 404
    assert client.delete(f"/api/documents/{created['id']}", headers=_auth(alice)).status_code == 404


def test_delete_own_document_removes_database_row_and_file(client, db):
    token = _register_and_login(client, "alice")
    created = _upload(client, token, "delete.txt", b"delete me").json()
    stored_path = resolve_upload_path(created["filename"])

    response = client.delete(f"/api/documents/{created['id']}", headers=_auth(token))

    assert response.status_code == 204
    assert db.get(Document, created["id"]) is None
    assert not stored_path.exists()
