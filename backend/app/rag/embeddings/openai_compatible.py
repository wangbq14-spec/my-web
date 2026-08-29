import httpx

from app.rag.embeddings.base import (
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingTimeoutError,
    EmbeddingUpstreamError,
)


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "",
        timeout: float = 30.0,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise EmbeddingConfigurationError("EMBEDDING_API_KEY 未配置")
        if not base_url:
            raise EmbeddingConfigurationError("EMBEDDING_BASE_URL 未配置")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        effective_model = self.model
        if not effective_model:
            raise EmbeddingConfigurationError("EMBEDDING_MODEL 未配置")

        try:
            response = self._client.post(
                f"{self.base_url}/embeddings",
                json={"model": effective_model, "input": texts},
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise EmbeddingTimeoutError("Embedding 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            raise EmbeddingUpstreamError(
                f"上游服务错误（HTTP {exc.response.status_code}）"
            ) from exc
        except httpx.RequestError as exc:
            raise EmbeddingUpstreamError("网络连接失败") from exc

        try:
            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError("上游返回格式异常") from exc

        if not all(
            isinstance(embedding, list)
            and all(isinstance(value, float) for value in embedding)
            for embedding in embeddings
        ):
            raise EmbeddingError("上游返回格式异常")

        return embeddings

    def embed_query(self, text: str) -> list[float]:
        try:
            return self.embed_texts([text])[0]
        except IndexError as exc:
            raise EmbeddingError("上游返回格式异常") from exc
