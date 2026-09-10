"""Offline mock provider mode: canned LLM/vision/embedding responses."""

import pytest
from sqlalchemy import select  # noqa: F401  (kept for parity with fixtures)

from app.core.config import settings
from app.llm.base import ImagePart, LLMMessage, TextPart
from app.llm.factory import get_llm_provider, get_vision_provider
from app.llm.mock import MockLLMProvider
from app.llm.registry import ModelRegistry, VisionNotSupportedError
from app.rag.embeddings.factory import MockEmbeddingProvider, get_embedding_provider


class _MockConfig:
    LLM_PROVIDER_LABEL = "mock"
    LLM_MODEL = "mock-model"
    VISION_MODEL = ""
    VISION_MODEL_TIER = "standard"
    TAOTOKEN_VISION_MODEL = ""


def test_mock_complete_returns_canned_content_and_usage():
    provider = MockLLMProvider()
    response = provider.complete([LLMMessage(role="user", content="你好")])
    assert response.content and "你好" in response.content
    assert response.usage is not None
    assert response.usage.prompt_tokens == 24
    assert response.usage.completion_tokens == 24


def test_mock_stream_yields_content_then_usage():
    provider = MockLLMProvider()
    chunks = list(provider.stream([LLMMessage(role="user", content="流式")]))
    assert chunks[-1].usage is not None
    assert any(chunk.content for chunk in chunks)


def test_mock_vision_answer_mentions_image():
    provider = MockLLMProvider()
    response = provider.complete([
        LLMMessage(role="user", content="请描述这张图片中的主要错误信息。",
                   content_parts=[TextPart(text="请描述这张图片中的主要错误信息。"),
                                  ImagePart(data_url_or_path="/tmp/x.png", mime_type="image/png")]),
    ])
    assert "[mock-vision]" in response.content


def test_mock_embedding_is_deterministic_and_fixed_dimension():
    provider = MockEmbeddingProvider(dimension=16)
    first = provider.embed_query("报销制度")
    second = provider.embed_query("报销制度")
    assert first == second and len(first) == 16
    assert all(isinstance(value, float) for value in first)
    texts = provider.embed_texts(["a", "b"])
    assert len(texts) == 2


def test_factories_select_mock_when_label_is_mock(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER_LABEL", "mock")
    monkeypatch.setattr(settings, "LLM_MODEL", "mock-model")
    monkeypatch.setattr(settings, "VISION_MODEL", "")
    monkeypatch.setattr(settings, "VISION_API_KEY", "")
    monkeypatch.setattr(settings, "VISION_BASE_URL", "")
    get_llm_provider.cache_clear()
    get_vision_provider.cache_clear()
    get_embedding_provider.cache_clear()
    try:
        assert isinstance(get_llm_provider(), MockLLMProvider)
        assert isinstance(get_vision_provider("mock"), MockLLMProvider)
        assert isinstance(get_embedding_provider(), MockEmbeddingProvider)
        # With VISION_* empty, openai_compatible falls back to the mock LLM.
        assert isinstance(get_vision_provider("openai_compatible"), MockLLMProvider)
    finally:
        get_llm_provider.cache_clear()
        get_vision_provider.cache_clear()
        get_embedding_provider.cache_clear()


def test_factories_vision_config_returns_openai_provider(monkeypatch):
    from app.llm.openai_compatible import OpenAICompatibleProvider

    monkeypatch.setattr(settings, "LLM_PROVIDER_LABEL", "openai_compatible")
    monkeypatch.setattr(settings, "VISION_MODEL", "vision-model-x")
    monkeypatch.setattr(settings, "VISION_API_KEY", "sk-x")
    monkeypatch.setattr(settings, "VISION_BASE_URL", "https://vision.example/v1")
    get_vision_provider.cache_clear()
    try:
        provider = get_vision_provider("openai_compatible")
        assert isinstance(provider, OpenAICompatibleProvider)
    finally:
        get_vision_provider.cache_clear()


def test_registry_vision_available_in_mock_mode():
    registry = ModelRegistry(_MockConfig())
    assert registry.capabilities("standard")["vision"] is True
    assert registry.capabilities("auto")["vision"] is False
    assert registry.resolve_for(capability="vision", tier="standard") == ("mock", "mock-model")


def test_registry_vision_unavailable_without_configuration():
    class _NoVisionConfig:
        LLM_PROVIDER_LABEL = "openai_compatible"
        VISION_MODEL = ""
        TAOTOKEN_VISION_MODEL = ""

    registry = ModelRegistry(_NoVisionConfig())
    with pytest.raises(VisionNotSupportedError):
        registry.resolve_for(capability="vision", tier="standard")


def test_vision_tier_auto_upgrade_selects_vision_provider(monkeypatch):
    """A vision request on a non-vision tier must be upgraded to the configured
    vision tier (server-authoritative) instead of failing."""
    from app.core.config import settings as real_settings
    from app.llm import factory as llm_factory
    from app.services import chat as chat_service

    captured = {}

    class _FakeProvider:
        pass

    def _fake_vision(label):
        captured["label"] = label
        return _FakeProvider()

    messages = [
        LLMMessage(role="user", content="看这张图",
                   content_parts=[TextPart(text="看这张图"),
                                  ImagePart(data_url_or_path="/tmp/x.png", mime_type="image/png")]),
    ]
    monkeypatch.setattr(real_settings, "VISION_MODEL_TIER", "standard")
    monkeypatch.setattr(real_settings, "VISION_BASE_CREDIT_COST", 0)
    monkeypatch.setattr(chat_service, "get_vision_provider", _fake_vision)
    monkeypatch.setattr(chat_service, "require_balance", lambda *a, **k: None)

    class _Registry:
        def capabilities(self, tier):
            # auto lacks vision, standard has it -> upgrade must happen.
            return {"vision": tier == "standard"}

        def resolve_for(self, *, capability, tier):
            captured["tier"] = tier
            assert capability == "vision" and tier == "standard"
            return "mock", "vision-model-x"

    monkeypatch.setattr(chat_service, "get_model_registry", lambda: _Registry())
    monkeypatch.setattr(chat_service, "get_llm_provider", lambda: _FakeProvider())

    provider, model, provider_label = chat_service._select_provider(None, 1, messages, "auto", None)
    assert captured["tier"] == "standard"
    assert model == "vision-model-x"
    assert provider_label == "mock"
    assert isinstance(provider, _FakeProvider)
