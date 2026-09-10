from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.api.routes import documents
from app.models.document import Document
from app.models.user import User, utcnow_naive
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
    return client.post(
        "/api/auth/login", json={"username": username, "password": "secret123"}
    ).json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _document(db, username: str, *, status: str) -> Document:
    user = db.query(User).filter_by(username=username).one()
    document = Document(
        user_id=user.id,
        filename=f"{username}-{status}.txt",
        original_filename="retry.txt",
        content_type="text/plain",
        file_size=5,
        status=status,
        error_code="parse_error" if status == "failed" else None,
        error_message="could not parse" if status == "failed" else None,
        retry_count=2 if status == "failed" else 0,
    )
    db.add(document)
    db.commit()
    return document


def test_retry_failed_document_queues_and_enqueues(client, db, fake_document_dispatcher):
    token = _register_and_login(client, "alice")
    document = _document(db, "alice", status="failed")

    response = client.post(f"/api/documents/{document.id}/retry", headers=_auth(token))

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["error_code"] is None
    assert response.json()["error_message"] is None
    assert response.json()["retry_count"] == 0
    assert db.get(Document, document.id).status == "queued"
    assert fake_document_dispatcher.enqueued_ids == [document.id]
    assert db.get(Document, document.id).next_retry_at is not None


def test_retry_other_users_document_returns_404(client, db):
    alice = _register_and_login(client, "alice")
    _register_and_login(client, "bob")
    document = _document(db, "bob", status="failed")

    response = client.post(f"/api/documents/{document.id}/retry", headers=_auth(alice))

    assert response.status_code == 404


@pytest.mark.parametrize("document_status", ["queued", "processing", "ready"])
def test_retry_non_failed_document_returns_409(client, db, document_status):
    token = _register_and_login(client, "alice")
    document = _document(db, "alice", status=document_status)

    response = client.post(f"/api/documents/{document.id}/retry", headers=_auth(token))

    assert response.status_code == 409
    assert db.get(Document, document.id).status == document_status


def test_retry_double_click_only_transitions_and_enqueues_once(
    client, db, fake_document_dispatcher
):
    token = _register_and_login(client, "alice")
    document = _document(db, "alice", status="failed")

    first = client.post(f"/api/documents/{document.id}/retry", headers=_auth(token))
    second = client.post(f"/api/documents/{document.id}/retry", headers=_auth(token))

    assert first.status_code == 202
    assert second.status_code == 409
    assert db.get(Document, document.id).status == "queued"
    assert fake_document_dispatcher.enqueued_ids == [document.id]


def test_retry_enqueue_failure_can_be_resubmitted_by_dispatcher_after_due_time(
    client, db, monkeypatch
):
    token = _register_and_login(client, "alice")
    document = _document(db, "alice", status="failed")
    document.processing_generation = 2
    db.commit()

    class FailingDispatcher:
        def enqueue(self, document_id: int) -> None:
            raise ConnectionError(f"queue unavailable for {document_id}")

    monkeypatch.setattr(documents, "get_document_task_dispatcher", FailingDispatcher)
    response = client.post(f"/api/documents/{document.id}/retry", headers=_auth(token))

    assert response.status_code == 202
    db.expire_all()
    retried = db.get(Document, document.id)
    assert retried.status == "queued"
    assert retried.processing_generation == 2
    assert retried.next_retry_at is None

    retried.next_retry_at = utcnow_naive() - timedelta(seconds=1)
    db.commit()
    dispatcher = FakeDocumentTaskDispatcher()
    set_document_task_dispatcher_for_test(dispatcher)
    try:
        assert schedule_pending_documents(lambda: sessionmaker(bind=db.get_bind())()) == 1
    finally:
        set_document_task_dispatcher_for_test(None)

    assert dispatcher.enqueued_ids == [document.id]
