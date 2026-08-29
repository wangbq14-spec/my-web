from functools import lru_cache

from app.core.config import settings
from app.rag.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider


@lru_cache
def get_embedding_provider() -> OpenAICompatibleEmbeddingProvider:
    return OpenAICompatibleEmbeddingProvider(
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL,
        model=settings.EMBEDDING_MODEL,
        timeout=settings.EMBEDDING_TIMEOUT,
    )
