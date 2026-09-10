from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app import worker
from app.api.routes import documents
from app.core.config import settings
from app.models.document import Document, DocumentChunk
from app.rag.storage import StorageSecurityError, resolve_upload_path
from app.rag.vector_store.db import DbVectorStore
from app.services.document import mark_ready
from app.services.document_tasks import (
    FakeDocumentTaskDispatcher,
    schedule_pending_documents,
    set_document_task_dispatcher_for_test,
)


@pytest.fixture(autouse=True)
def fake_document_dispatcher(monkeypatch):
    dispatcher = FakeDocumentTaskDispatcher()
    monkeypatch.setattr(documents, "get_document_task_dispatcher", lambda: dispatcher)
    return dispatcher


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


def test_upload_is_accepted_queued_and_enqueued(client, fake_document_dispatcher):
    token = _register_and_login(client, "alice")

    txt = _upload(client, token, "notes.txt", b"hello")
    markdown = _upload(client, token, "notes.md", b"# heading")

    assert txt.status_code == 202
    assert markdown.status_code == 202
    assert txt.json()["status"] == "queued"
    assert txt.json()["original_filename"] == "notes.txt"
    assert txt.json()["filename"].endswith(".txt")
    assert txt.json()["content_type"] == "text/plain"
    assert txt.json()["project_id"] is None
    assert markdown.json()["content_type"] == "text/markdown"
    assert "user_id" not in txt.json()
    assert fake_document_dispatcher.enqueued_ids == [txt.json()["id"], markdown.json()["id"]]


def test_upload_cooldown_prevents_duplicate_dispatcher_delivery(client, db):
    token = _register_and_login(client, "alice")

    response = _upload(client, token, "notes.txt", b"hello")

    assert response.status_code == 202
    document = db.get(Document, response.json()["id"])
    assert document.next_retry_at is not None
    dispatcher = FakeDocumentTaskDispatcher()
    set_document_task_dispatcher_for_test(dispatcher)
    try:
        assert schedule_pending_documents(lambda: sessionmaker(bind=db.get_bind())()) == 0
    finally:
        set_document_task_dispatcher_for_test(None)
    assert dispatcher.enqueued_ids == []


def test_upload_enqueue_failure_keeps_queued_document_and_file(client, db, monkeypatch):
    token = _register_and_login(client, "alice")

    class FailingDispatcher:
        def enqueue(self, document_id: int) -> None:
            raise ConnectionError(f"queue unavailable for {document_id}")

    monkeypatch.setattr(documents, "get_document_task_dispatcher", FailingDispatcher)
    response = _upload(client, token, "notes.txt", b"hello")

    assert response.status_code == 202
    created = response.json()
    assert db.get(Document, created["id"]).status == "queued"
    assert resolve_upload_path(created["filename"]).is_file()


def test_upload_rejects_unsupported_extension(client):
    token = _register_and_login(client, "alice")

    response = _upload(client, token, "malware.exe", b"not executable")

    assert response.status_code == 422
    assert response.json()["detail"] == "\u4e0d\u652f\u6301\u7684\u6587\u4ef6\u7c7b\u578b"


def test_upload_rejects_empty_file(client):
    token = _register_and_login(client, "alice")

    response = _upload(client, token, "empty.txt", b"")

    assert response.status_code == 422
    assert response.json()["detail"] == "\u6587\u4ef6\u4e3a\u7a7a"


def test_upload_rejects_too_large_file(client, monkeypatch):
    token = _register_and_login(client, "alice")
    monkeypatch.setattr(settings, "RAG_MAX_UPLOAD_BYTES", 3)

    response = _upload(client, token, "large.txt", b"1234")

    assert response.status_code == 413
    assert response.json()["detail"] == "\u6587\u4ef6\u8fc7\u5927"


def test_upload_uses_internal_safe_filename(client):
    token = _register_and_login(client, "alice")

    response = _upload(client, token, "../../outside.txt", b"safe")

    assert response.status_code == 202
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


def test_list_only_contains_current_users_active_documents(client):
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


def test_delete_soft_deletes_file_chunks_and_fences_worker(client, db):
    token = _register_and_login(client, "alice")
    created = _upload(client, token, "delete.txt", b"delete me").json()
    stored_path = resolve_upload_path(created["filename"])
    document = db.get(Document, created["id"])
    document.status = "processing"
    document.processing_token = "worker-token"
    document.processing_generation = 4
    db.add(
        DocumentChunk(
            document_id=document.id,
            generation=4,
            chunk_index=0,
            content="staging",
            char_count=7,
        )
    )
    db.commit()

    response = client.delete(f"/api/documents/{created['id']}", headers=_auth(token))

    assert response.status_code == 204
    deleted = db.get(Document, created["id"])
    assert deleted.status == "deleted"
    assert deleted.deleted_at is not None
    assert deleted.processing_token is None
    assert deleted.processing_generation == 5
    assert db.query(DocumentChunk).filter_by(document_id=created["id"]).all() == []
    assert not stored_path.exists()
    assert client.get(f"/api/documents/{created['id']}", headers=_auth(token)).status_code == 404
    assert client.get("/api/documents", headers=_auth(token)).json() == []
    assert mark_ready(db, created["id"], deleted.user_id, "worker-token", 4) is False
    db.commit()
    db.refresh(deleted)
    assert deleted.status == "deleted"


def test_delete_file_failure_rolls_back_soft_delete(client, db, monkeypatch):
    token = _register_and_login(client, "alice")
    created = _upload(client, token, "delete.txt", b"delete me").json()
    document = db.get(Document, created["id"])
    db.add(
        DocumentChunk(
            document_id=document.id,
            generation=0,
            chunk_index=0,
            content="preserve on file failure",
            char_count=24,
            embedding="[1.0, 0.0]",
        )
    )
    db.commit()

    def fail_delete_upload(_filename: str) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(documents, "delete_upload", fail_delete_upload)

    response = client.delete(f"/api/documents/{created['id']}", headers=_auth(token))

    assert response.status_code == 500
    assert response.json()["detail"] == "删除失败，请重试"
    db.expire_all()
    document = db.get(Document, created["id"])
    assert document.status == "queued"
    assert document.deleted_at is None
    assert db.query(DocumentChunk).filter_by(document_id=document.id).count() == 1
    assert client.get(f"/api/documents/{created['id']}", headers=_auth(token)).status_code == 200


def test_delete_ready_document_commit_failure_keeps_doc_and_retry_succeeds(
    client, db, monkeypatch
):
    token = _register_and_login(client, "alice")
    created = _upload(client, token, "ready-delete.txt", b"delete me").json()
    stored_path = resolve_upload_path(created["filename"])
    document = db.get(Document, created["id"])
    document.status = "ready"
    document.processing_generation = 1
    document.active_generation = 1
    db.add(
        DocumentChunk(
            document_id=document.id,
            generation=1,
            chunk_index=0,
            content="searchable before delete",
            char_count=24,
            embedding="[1.0, 0.0]",
        )
    )
    db.commit()
    store = DbVectorStore(sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False))

    assert [match.document_id for match in store.search(document.user_id, [1.0, 0.0], 5)] == [
        document.id
    ]

    original_commit = db.commit

    def fail_commit() -> None:
        raise OperationalError("COMMIT", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(db, "commit", fail_commit)
    response = client.delete(f"/api/documents/{document.id}", headers=_auth(token))
    monkeypatch.setattr(db, "commit", original_commit)

    assert response.status_code == 500
    assert not stored_path.exists()
    db.expire_all()
    retained = db.get(Document, document.id)
    assert retained.status == "ready"
    assert retained.deleted_at is None
    assert db.query(DocumentChunk).filter_by(document_id=document.id).count() == 1
    assert [match.document_id for match in store.search(retained.user_id, [1.0, 0.0], 5)] == [
        retained.id
    ]

    retry_response = client.delete(f"/api/documents/{retained.id}", headers=_auth(token))

    assert retry_response.status_code == 204
    db.expire_all()
    deleted = db.get(Document, retained.id)
    assert deleted.status == "deleted"
    assert deleted.deleted_at is not None
    assert db.query(DocumentChunk).filter_by(document_id=deleted.id).count() == 0
    assert store.search(deleted.user_id, [1.0, 0.0], 5) == []
    assert client.get(f"/api/documents/{deleted.id}", headers=_auth(token)).status_code == 404


def test_delete_commit_failure_keeps_document_visible_and_missing_file_fails_safely(
    client, db, monkeypatch
):
    token = _register_and_login(client, "alice")
    created = _upload(client, token, "delete.txt", b"delete me").json()
    stored_path = resolve_upload_path(created["filename"])
    original_commit = db.commit

    def fail_commit() -> None:
        raise OperationalError("COMMIT", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(db, "commit", fail_commit)
    response = client.delete(f"/api/documents/{created['id']}", headers=_auth(token))
    monkeypatch.setattr(db, "commit", original_commit)

    assert response.status_code == 500
    assert not stored_path.exists()
    db.expire_all()
    document = db.get(Document, created["id"])
    assert document.status == "queued"
    assert document.deleted_at is None
    assert client.get(f"/api/documents/{created['id']}", headers=_auth(token)).status_code == 200

    monkeypatch.setattr(
        worker, "SessionLocal", lambda: sessionmaker(bind=db.get_bind())()
    )
    worker.process_document_task(document.id)

    db.expire_all()
    failed = db.get(Document, document.id)
    assert failed.status == "failed"
    assert failed.error_code == "parse_error"
    failed_response = client.get(f"/api/documents/{document.id}", headers=_auth(token))
    assert failed_response.status_code == 200
    assert str(stored_path) not in failed_response.text
    assert created["filename"] not in failed_response.json()["error_message"]
