from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.rag.embeddings.factory import get_embedding_provider
from app.rag.vector_store.factory import get_vector_store


@dataclass
class RetrievedChunk:
    document_id: int
    filename: str
    chunk_index: int
    content: str
    score: float


def retrieve(
    session: Session,
    user_id: int,
    query: str,
    top_k: int = 5,
    project_id: int | None = None,
) -> list[RetrievedChunk]:
    embedding = get_embedding_provider().embed_query(query)
    if project_id is None:
        results = get_vector_store().search(user_id, embedding, top_k)
    else:
        results = get_vector_store().search(
            user_id, embedding, top_k, project_id=project_id
        )
    document_ids = {result.document_id for result in results}
    if not document_ids:
        return []

    conditions = [
        Document.id.in_(document_ids),
        Document.user_id == user_id,
        Document.deleted_at.is_(None),
    ]
    if project_id is not None:
        conditions.append(Document.project_id == project_id)
    documents = session.execute(
        select(Document.id, Document.original_filename).where(*conditions)
    ).all()
    filenames = {document_id: filename for document_id, filename in documents}
    return [
        RetrievedChunk(
            document_id=result.document_id,
            filename=filenames[result.document_id],
            chunk_index=result.chunk_index,
            content=result.content,
            score=result.score,
        )
        for result in results
        if result.document_id in filenames
    ]
