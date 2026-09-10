from functools import lru_cache

from app.core.config import settings
from app.rag.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider


class MockEmbeddingProvider:
    """Deterministic offline embeddings (fixed dimension) for tests/capacity."""

    def __init__(self, dimension: int = 16) -> None:
        self._dimension = dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        h = sum(ord(ch) * (i + 1) for i, ch in enumerate(text))
        vector[abs(h) % self._dimension] = 1.0
        return vector


@lru_cache
def get_embedding_provider():
    if settings.LLM_PROVIDER_LABEL == "mock":
        return MockEmbeddingProvider()
    return OpenAICompatibleEmbeddingProvider(
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_BASE_URL,
        model=settings.EMBEDDING_MODEL,
        timeout=settings.EMBEDDING_TIMEOUT,
    )
