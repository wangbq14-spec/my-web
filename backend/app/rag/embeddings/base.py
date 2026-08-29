from abc import ABC, abstractmethod


class EmbeddingError(Exception):
    """Embedding provider base error."""


class EmbeddingConfigurationError(EmbeddingError):
    """Embedding provider configuration is missing or invalid."""


class EmbeddingTimeoutError(EmbeddingError):
    """Embedding request timed out."""


class EmbeddingUpstreamError(EmbeddingError):
    """Embedding provider network or HTTP request failed."""


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError
