from datetime import datetime, timedelta

from app.models.document import Document, DocumentChunk
from app.models.project import Project
from app.schemas.document import DocumentOut
from app.services.document import (
    claim_document,
    mark_failed,
    mark_ready,
    reclaim_expired,
    reset_for_manual_retry,
    soft_delete_document,
)
from app.models.user import utcnow_naive


def _document(*, user_id: int = 1, **values) -> Document:
    return Document(
        user_id=user_id,
        filename="stored.txt",
        original_filename="original.txt",
        content_type="text/plain",
        file_size=5,
        **values,
    )


def test_claim_document_is_atomic_and_rejects_deleted_documents(db):
    queued = _document()
    deleted = _document(status="queued", deleted_at=utcnow_naive())
    db.add_all([queued, deleted])
    db.commit()

    assert claim_document(db, queued.id, 1, "token-1", 60) is True
    assert claim_document(db, queued.id, 1, "token-2", 60) is False
    assert claim_document(db, deleted.id, 1, "token-3", 60) is False
    db.commit()

    db.refresh(queued)
    assert queued.status == "processing"
    assert queued.processing_token == "token-1"
    assert queued.processing_generation == 1
    assert queued.processing_started_at is not None
    assert queued.processing_lease_expires_at is not None


def test_reclaim_expired_replaces_the_lease_and_bumps_generation(db):
    expired = _document(
        status="processing",
        processing_token="old-token",
        processing_generation=1,
        processing_lease_expires_at=utcnow_naive() - timedelta(seconds=1),
    )
    active = _document(
        status="processing",
        processing_token="active-token",
        processing_lease_expires_at=utcnow_naive() + timedelta(seconds=60),
    )
    db.add_all([expired, active])
    db.commit()

    assert reclaim_expired(db, expired.id, 1, "new-token", 60) is True
    assert reclaim_expired(db, active.id, 1, "other-token", 60) is False
    db.commit()

    db.refresh(expired)
    assert expired.processing_token == "new-token"
    assert expired.processing_generation == 2


def test_mark_ready_publishes_generation_and_removes_older_chunks(db):
    document = _document(
        status="processing", processing_token="token-1", processing_generation=2
    )
    db.add(document)
    db.flush()
    db.add_all(
        [
            DocumentChunk(
                document_id=document.id,
                generation=1,
                chunk_index=0,
                content="old",
                char_count=3,
            ),
            DocumentChunk(
                document_id=document.id,
                generation=2,
                chunk_index=0,
                content="new",
                char_count=3,
            ),
        ]
    )
    db.commit()

    assert mark_ready(db, document.id, 1, "token-1", 2) is True
    db.commit()

    db.refresh(document)
    assert document.status == "ready"
    assert document.active_generation == 2
    assert document.processing_token is None
    assert document.processed_at is not None
    assert [chunk.generation for chunk in document_chunks(db, document.id)] == [2]


def test_mark_ready_touches_owning_project(db):
    project = Project(user_id=1, name="project")
    db.add(project)
    db.flush()
    document = _document(
        project_id=project.id,
        status="processing",
        processing_token="token-1",
        processing_generation=1,
    )
    db.add(document)
    db.commit()
    old_activity = datetime(2020, 1, 1, 0, 0, 0)
    project.last_activity_at = old_activity
    db.commit()

    assert mark_ready(db, document.id, 1, "token-1", 1) is True
    db.commit()

    db.refresh(project)
    assert project.last_activity_at > old_activity


def test_mark_ready_rejects_wrong_token_or_generation(db):
    document = _document(
        status="processing", processing_token="token-1", processing_generation=2
    )
    db.add(document)
    db.commit()

    assert mark_ready(db, document.id, 1, "wrong-token", 2) is False
    assert mark_ready(db, document.id, 1, "token-1", 1) is False
    db.refresh(document)
    assert document.status == "processing"
    assert document.active_generation == 0


def test_mark_failed_schedules_retry_with_incremented_count(db):
    document = _document(status="processing", processing_token="token-1")
    db.add(document)
    db.commit()
    before = utcnow_naive()

    assert (
        mark_failed(
            db,
            document.id,
            1,
            "embedding_unavailable",
            "embedding unavailable",
            True,
            3,
            10,
            60,
        )
        == "queued"
    )
    db.commit()

    db.refresh(document)
    assert document.status == "queued"
    assert document.retry_count == 1
    assert document.next_retry_at is not None
    assert before <= document.next_retry_at <= before + timedelta(seconds=10.1)
    assert document.processing_token is None


def test_mark_failed_terminally_removes_staging_chunks(db):
    document = _document(
        status="processing", processing_token="token-1", processing_generation=4
    )
    db.add(document)
    db.flush()
    db.add_all(
        [
            DocumentChunk(
                document_id=document.id,
                generation=3,
                chunk_index=0,
                content="active",
                char_count=6,
            ),
            DocumentChunk(
                document_id=document.id,
                generation=4,
                chunk_index=0,
                content="staging",
                char_count=7,
            ),
        ]
    )
    db.commit()

    assert (
        mark_failed(
            db,
            document.id,
            1,
            "parse_error",
            "could not parse",
            False,
            3,
            10,
            60,
        )
        == "failed"
    )
    db.commit()

    db.refresh(document)
    assert document.status == "failed"
    assert document.error_code == "parse_error"
    assert document.error_message == "could not parse"
    assert document.processing_token is None
    assert document_chunks(db, document.id) == []


def test_terminal_failure_touches_owning_project(db):
    project = Project(user_id=1, name="project")
    db.add(project)
    db.flush()
    document = _document(
        project_id=project.id,
        status="processing",
        processing_token="token-1",
    )
    db.add(document)
    db.commit()
    old_activity = datetime(2020, 1, 1, 0, 0, 0)
    project.last_activity_at = old_activity
    db.commit()

    result = mark_failed(
        db,
        document.id,
        1,
        "parse_error",
        "could not parse",
        False,
        3,
        10,
        60,
    )
    db.commit()

    assert result == "failed"
    db.refresh(project)
    assert project.last_activity_at > old_activity


def test_manual_retry_only_transitions_failed_document_once(db):
    document = _document(status="failed", error_code="parse_error", retry_count=2)
    queued = _document(status="queued")
    db.add_all([document, queued])
    db.commit()

    assert reset_for_manual_retry(db, document.id, 1) is True
    assert reset_for_manual_retry(db, document.id, 1) is False
    assert reset_for_manual_retry(db, queued.id, 1) is False
    db.commit()

    db.refresh(document)
    assert document.status == "queued"
    assert document.error_code is None
    assert document.error_message is None
    assert document.retry_count == 0
    assert document.next_retry_at is None


def test_soft_delete_clears_token_and_invalidates_generation(db):
    document = _document(
        status="processing", processing_token="token-1", processing_generation=5
    )
    db.add(document)
    db.commit()

    assert soft_delete_document(db, document.id, 1) is True
    assert soft_delete_document(db, document.id, 1) is False
    db.commit()

    db.refresh(document)
    assert document.status == "deleted"
    assert document.deleted_at is not None
    assert document.processing_token is None
    assert document.processing_generation == 6


def test_document_out_exposes_safe_async_status_fields(db):
    document = _document(
        status="ready",
        error_code="old_error",
        retry_count=2,
        active_generation=3,
        processing_generation=4,
        processed_at=utcnow_naive(),
    )
    db.add(document)
    db.commit()

    output = DocumentOut.model_validate(document)

    assert output.error_code == "old_error"
    assert output.retry_count == 2
    assert output.active_generation == 3
    assert output.processing_generation == 4
    assert output.processed_at == document.processed_at
    assert "processing_token" not in output.model_dump()
    assert "processing_lease_expires_at" not in output.model_dump()
    assert "next_retry_at" not in output.model_dump()


def document_chunks(db, document_id: int) -> list[DocumentChunk]:
    return list(
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.generation)
    )
