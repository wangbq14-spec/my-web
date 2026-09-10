"""Recovery helpers for documents created before durable embeddings."""

from sqlalchemy import exists, or_, select, update
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk


def mark_ready_documents_for_reindex(session: Session) -> int:
    """Queue ready, non-deleted documents that lack durable embeddings.

    The caller owns the transaction. Existing chunks are deliberately retained:
    the processing generation fence replaces them only after successful embedding.
    """
    has_chunk_without_embedding = exists(
        select(DocumentChunk.id).where(
            DocumentChunk.document_id == Document.id,
            DocumentChunk.embedding.is_(None),
        )
    )
    has_any_chunk = exists(
        select(DocumentChunk.id).where(DocumentChunk.document_id == Document.id)
    )
    result = session.execute(
        update(Document)
        .where(
            Document.status == "ready",
            Document.deleted_at.is_(None),
            or_(has_chunk_without_embedding, ~has_any_chunk),
        )
        .values(
            status="queued",
            active_generation=0,
            error_code=None,
            error_message=None,
            next_retry_at=None,
        )
    )
    return result.rowcount
