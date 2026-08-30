import json
import math
from collections.abc import Callable

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.rag.vector_store.base import ChunkVector, ScoredChunk, VectorStore


class DocumentProcessingCancelled(ValueError):
    """Raised when a worker no longer owns a document processing generation."""


class DbVectorStore(VectorStore):
    """Durable vector store backed by document chunks in the application database."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def upsert_chunks(
        self,
        user_id: int,
        document_id: int,
        generation: int,
        chunks: list[ChunkVector],
    ) -> None:
        session = self._session_factory()
        try:
            # This conditional write is both the generation eligibility check and
            # the write fence.  Keeping it in the chunk transaction means a
            # concurrent delete or lease reclaim is serialized with the chunk
            # replacement rather than racing a non-locking read.
            result = session.execute(
                update(Document)
                .where(
                    Document.id == document_id,
                    Document.user_id == user_id,
                    Document.status == "processing",
                    Document.deleted_at.is_(None),
                    Document.processing_generation == generation,
                )
                .values(processing_started_at=Document.processing_started_at)
            )
            if result.rowcount != 1:
                raise DocumentProcessingCancelled(
                    "Document is not available for this processing generation"
                )

            session.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.generation == generation,
                )
            )
            session.add_all(
                [
                    DocumentChunk(
                        document_id=document_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        char_count=len(chunk.content),
                        embedding=json.dumps(list(chunk.embedding)),
                        generation=generation,
                    )
                    for chunk in chunks
                ]
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def search(
        self,
        user_id: int,
        query_embedding: list[float],
        top_k: int,
        project_id: int | None = None,
    ) -> list[ScoredChunk]:
        if top_k <= 0:
            return []

        session = self._session_factory()
        try:
            conditions = [
                Document.user_id == user_id,
                Document.status == "ready",
                Document.deleted_at.is_(None),
                DocumentChunk.generation == Document.active_generation,
            ]
            if project_id is not None:
                conditions.append(Document.project_id == project_id)

            rows = session.execute(
                select(
                    DocumentChunk.document_id,
                    DocumentChunk.chunk_index,
                    DocumentChunk.content,
                    DocumentChunk.embedding,
                )
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(*conditions)
            ).all()

            matches: list[ScoredChunk] = []
            for document_id, chunk_index, content, embedding_json in rows:
                embedding = self._load_embedding(embedding_json)
                if embedding is None:
                    continue
                matches.append(
                    ScoredChunk(
                        document_id=document_id,
                        chunk_index=chunk_index,
                        content=content,
                        score=self._cosine_similarity(query_embedding, embedding),
                    )
                )
            matches.sort(key=lambda match: match.score, reverse=True)
            session.commit()
            return matches[:top_k]
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete_document(self, user_id: int, document_id: int) -> None:
        session = self._session_factory()
        try:
            document = session.get(Document, document_id)
            if document is not None and document.user_id == user_id:
                session.execute(
                    delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
                )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _load_embedding(value: str) -> list[float] | None:
        try:
            embedding = json.loads(value)
        except (TypeError, ValueError):
            return None
        if not isinstance(embedding, list) or not all(
            isinstance(item, int | float) for item in embedding
        ):
            return None
        return [float(item) for item in embedding]

    @staticmethod
    def _cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
        dot = sum(a * b for a, b in zip(vector_a, vector_b, strict=False))
        norm_a = math.sqrt(sum(value * value for value in vector_a))
        norm_b = math.sqrt(sum(value * value for value in vector_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
