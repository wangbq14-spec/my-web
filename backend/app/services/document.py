from datetime import timedelta
from random import uniform

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.models.user import utcnow_naive
from app.services.project import touch_project_activity


def create_document(
    session: Session,
    *,
    user_id: int,
    filename: str,
    original_filename: str,
    content_type: str | None,
    file_size: int,
    project_id: int | None = None,
) -> Document:
    document = Document(
        user_id=user_id,
        filename=filename,
        original_filename=original_filename,
        content_type=content_type,
        file_size=file_size,
        project_id=project_id,
        status="queued",
    )
    session.add(document)
    session.flush()
    session.refresh(document)
    return document


def list_documents(session: Session, *, user_id: int) -> list[Document]:
    result = session.execute(
        select(Document)
        .where(Document.user_id == user_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    return list(result.scalars().all())


def get_document(
    session: Session,
    *,
    user_id: int,
    document_id: int,
) -> Document | None:
    return session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.deleted_at.is_(None),
        )
    )


def update_document_project(
    session: Session, *, document: Document, project_id: int | None
) -> Document:
    original_project_id = document.project_id
    document.project_id = project_id
    session.flush()
    for affected_project_id in {
        value for value in (original_project_id, project_id) if value is not None
    }:
        touch_project_activity(session, affected_project_id)
    return document


def delete_document_chunks(session: Session, *, document_id: int) -> None:
    """Remove all durable vector chunks in the caller's transaction."""
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )


def delete_document(
    session: Session,
    *,
    user_id: int,
    document_id: int,
) -> Document | None:
    """Legacy physical deletion helper kept for non-API callers."""
    document = get_document(session, user_id=user_id, document_id=document_id)
    if document is None:
        return None
    original_project_id = document.project_id
    delete_document_chunks(session, document_id=document_id)
    session.delete(document)
    session.flush()
    if original_project_id is not None:
        touch_project_activity(session, original_project_id)
    return document


def claim_document(
    session: Session,
    document_id: int,
    user_id: int,
    token: str,
    lease_seconds: float,
) -> bool:
    """Claim a queued document without committing the caller's transaction."""
    now = utcnow_naive()
    result = session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status == "queued",
            Document.deleted_at.is_(None),
        )
        .values(
            status="processing",
            processing_token=token,
            processing_generation=Document.processing_generation + 1,
            next_retry_at=None,
            processing_started_at=now,
            processing_lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
    )
    return result.rowcount == 1


def reclaim_expired(
    session: Session,
    document_id: int,
    user_id: int,
    token: str,
    lease_seconds: float,
) -> bool:
    """Take over a document whose processing lease has expired."""
    now = utcnow_naive()
    result = session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status == "processing",
            Document.processing_lease_expires_at < now,
            Document.deleted_at.is_(None),
        )
        .values(
            processing_token=token,
            processing_generation=Document.processing_generation + 1,
            processing_started_at=now,
            processing_lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
    )
    return result.rowcount == 1


def mark_ready(
    session: Session,
    document_id: int,
    user_id: int,
    token: str,
    generation: int,
) -> bool:
    """Publish a fenced processing generation and discard older chunks."""
    now = utcnow_naive()
    project_id = session.scalar(
        select(Document.project_id).where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status == "processing",
            Document.processing_token == token,
            Document.processing_generation == generation,
            Document.deleted_at.is_(None),
        )
    )
    result = session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status == "processing",
            Document.processing_token == token,
            Document.processing_generation == generation,
            Document.deleted_at.is_(None),
        )
        .values(
            active_generation=generation,
            status="ready",
            processed_at=now,
            error_code=None,
            error_message=None,
            processing_token=None,
        )
    )
    if result.rowcount != 1:
        return False

    session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.generation < generation,
        )
    )
    if project_id is not None:
        touch_project_activity(session, project_id)
    return True


def _retry_delay_seconds(
    retry_count: int, base_seconds: float, max_seconds: float
) -> float:
    capped_delay = min(max_seconds, base_seconds * (2**retry_count))
    return uniform(0, capped_delay)


def mark_failed(
    session: Session,
    document_id: int,
    user_id: int,
    error_code: str,
    error_message: str,
    retryable: bool,
    retry_count_cap: int,
    base_seconds: float,
    max_seconds: float,
    token: str | None = None,
    generation: int | None = None,
) -> str:
    """Record a failure, scheduling retry when the retry budget permits it."""
    now = utcnow_naive()
    ownership_conditions = [
        Document.id == document_id,
        Document.user_id == user_id,
        Document.status == "processing",
    ]
    if token is not None:
        ownership_conditions.append(Document.processing_token == token)
    if generation is not None:
        ownership_conditions.append(Document.processing_generation == generation)
    project_id = session.scalar(
        select(Document.project_id).where(*ownership_conditions)
    )

    if retryable:
        document = session.scalar(
            select(Document).where(
                *ownership_conditions,
                Document.retry_count < retry_count_cap,
            )
        )
        if document is not None:
            next_retry_at = now + timedelta(
                seconds=_retry_delay_seconds(
                    document.retry_count, base_seconds, max_seconds
                )
            )
            result = session.execute(
                update(Document)
                .where(
                    *ownership_conditions,
                    Document.retry_count < retry_count_cap,
                )
                .values(
                    status="queued",
                    retry_count=Document.retry_count + 1,
                    next_retry_at=next_retry_at,
                    processing_token=None,
                    processing_lease_expires_at=None,
                )
            )
            if result.rowcount == 1:
                session.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
                )
                return "queued"

    result = session.execute(
        update(Document)
        .where(*ownership_conditions)
        .values(
            status="failed",
            error_code=error_code,
            error_message=error_message,
            processing_token=None,
            processing_lease_expires_at=None,
        )
    )
    if result.rowcount == 1:
        session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        if project_id is not None:
            touch_project_activity(session, project_id)
        return "failed"
    return "cancelled"


def reset_for_manual_retry(session: Session, document_id: int, user_id: int) -> bool:
    """Atomically put one failed document back into the queue."""
    result = session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status == "failed",
            Document.deleted_at.is_(None),
        )
        .values(
            status="queued",
            error_code=None,
            error_message=None,
            retry_count=0,
            next_retry_at=None,
        )
    )
    return result.rowcount == 1


def soft_delete_document(session: Session, document_id: int, user_id: int) -> bool:
    """Invalidate active workers while retaining the document record."""
    project_id = session.scalar(
        select(Document.project_id).where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status != "deleted",
        )
    )
    result = session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.status != "deleted",
        )
        .values(
            status="deleted",
            deleted_at=utcnow_naive(),
            processing_token=None,
            processing_generation=Document.processing_generation + 1,
            processing_lease_expires_at=None,
        )
    )
    if result.rowcount != 1:
        return False
    if project_id is not None:
        touch_project_activity(session, project_id)
    return True
