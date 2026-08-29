from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk


def create_document(
    session: Session,
    *,
    user_id: int,
    filename: str,
    original_filename: str,
    content_type: str | None,
    file_size: int,
) -> Document:
    document = Document(
        user_id=user_id,
        filename=filename,
        original_filename=original_filename,
        content_type=content_type,
        file_size=file_size,
        status="processing",
    )
    session.add(document)
    session.flush()
    session.refresh(document)
    return document


def list_documents(session: Session, *, user_id: int) -> list[Document]:
    result = session.execute(
        select(Document)
        .where(Document.user_id == user_id)
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
        )
    )


def delete_document(
    session: Session,
    *,
    user_id: int,
    document_id: int,
) -> Document | None:
    document = get_document(session, user_id=user_id, document_id=document_id)
    if document is None:
        return None
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )
    session.delete(document)
    session.flush()
    return document
