from functools import lru_cache

from app.db.session import SessionLocal
from app.rag.vector_store.db import DbVectorStore
from app.rag.vector_store.base import VectorStore


@lru_cache
def get_vector_store() -> VectorStore:
    """Return the durable store shared by the API and worker processes."""
    return DbVectorStore(SessionLocal)
