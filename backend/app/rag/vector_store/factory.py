from functools import lru_cache

from app.rag.vector_store.local import LocalVectorStore


@lru_cache
def get_vector_store() -> LocalVectorStore:
    return LocalVectorStore()
