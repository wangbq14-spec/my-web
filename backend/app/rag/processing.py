from pathlib import Path

from sqlalchemy.orm import Session

from app.models.document import Document, DocumentChunk
from app.rag import chunking, storage
from app.rag.embeddings.factory import get_embedding_provider
from app.rag.parsers import parse_document
from app.rag.parsers.base import ParserError
from app.rag.vector_store.base import ChunkVector
from app.rag.vector_store.factory import get_vector_store


def process_document(session: Session, user_id: int, document: Document) -> Document:
    """Parse, chunk, embed, and index a persisted document without committing."""
    vector_store = None
    try:
        path = storage.resolve_upload_path(document.filename)
        parsed = parse_document(path, Path(document.filename).suffix.lower())
        chunks = chunking.chunk_text(parsed.text)
        if not chunks:
            raise ParserError("文档无可用内容")

        embeddings = get_embedding_provider().embed_texts(chunks)
        if len(embeddings) != len(chunks):
            from app.rag.embeddings.base import EmbeddingError

            raise EmbeddingError("Embedding 返回数量不匹配")

        for index, content in enumerate(chunks):
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    char_count=len(content),
                )
            )
        session.flush()

        vector_store = get_vector_store()
        vector_store.upsert_chunks(
            user_id,
            document.id,
            [
                ChunkVector(chunk_index=index, content=content, embedding=embedding)
                for index, (content, embedding) in enumerate(zip(chunks, embeddings))
            ],
        )
        document.status = "ready"
        document.error_message = None
        session.flush()
        return document
    except Exception:
        # An upsert implementation may have partially persisted before raising.
        # LocalVectorStore deletion is idempotent, so remove any such residue.
        if vector_store is not None:
            try:
                vector_store.delete_document(user_id, document.id)
            except Exception:
                pass
        raise
