import json

import httpx
import pytest

from app.rag.embeddings.base import (
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingTimeoutError,
    EmbeddingUpstreamError,
)
from app.rag.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(index)] for index, text in enumerate(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


def _provider(handler, *, api_key="sk-test", base_url="https://x/v1", model="embed-test"):
    return OpenAICompatibleEmbeddingProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_fake_provider_embed_texts_preserves_order():
    provider = FakeEmbeddingProvider()

    assert provider.embed_texts(["one", "three"]) == [[3.0, 0.0], [5.0, 1.0]]


def test_fake_provider_embed_query_returns_first_embedding():
    provider = FakeEmbeddingProvider()

    assert provider.embed_query("hello") == [5.0, 0.0]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"api_key": "", "base_url": "https://x/v1", "model": "embed"}, "EMBEDDING_API_KEY"),
        ({"api_key": "sk-test", "base_url": "", "model": "embed"}, "EMBEDDING_BASE_URL"),
    ],
)
def test_missing_provider_configuration_raises(kwargs, message):
    with pytest.raises(EmbeddingConfigurationError, match=message):
        OpenAICompatibleEmbeddingProvider(**kwargs)


def test_missing_model_configuration_raises():
    provider = _provider(lambda request: httpx.Response(200), model="")

    with pytest.raises(EmbeddingConfigurationError, match="EMBEDDING_MODEL"):
        provider.embed_texts(["hello"])


def test_embed_texts_posts_openai_compatible_payload_in_order():
    def handler(request):
        assert request.url == "https://x/v1/embeddings"
        assert request.headers["authorization"] == "Bearer sk-test"
        assert json.loads(request.content) == {
            "model": "embed-test",
            "input": ["first", "second"],
        }
        return httpx.Response(
            200,
            json={"data": [{"embedding": [1.0, 0.0]}, {"embedding": [0.0, 1.0]}]},
        )

    provider = _provider(handler)

    assert provider.embed_texts(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]


def test_timeout_maps_to_embedding_timeout_error():
    def handler(request):
        raise httpx.TimeoutException("timeout", request=request)

    with pytest.raises(EmbeddingTimeoutError):
        _provider(handler).embed_texts(["hello"])


def test_upstream_status_error_maps_to_embedding_upstream_error():
    provider = _provider(lambda request: httpx.Response(503, request=request))

    with pytest.raises(EmbeddingUpstreamError, match="HTTP 503"):
        provider.embed_texts(["hello"])


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500, request=request),
        lambda request: httpx.Response(200, json={"data": [{"embedding": [1]}]}),
    ],
)
def test_embedding_errors_do_not_leak_secrets(handler):
    base_url = "https://private-embedding.example/v1"
    provider = _provider(handler, api_key="SUPERSECRET", base_url=base_url)

    with pytest.raises((EmbeddingUpstreamError, EmbeddingError)) as exc_info:
        provider.embed_texts(["hello"])

    assert "SUPERSECRET" not in str(exc_info.value)
    assert base_url not in str(exc_info.value)
