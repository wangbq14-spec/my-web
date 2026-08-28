import json

import httpx
import pytest

from app.core.config import settings
from app.llm.base import (
    LLMConfigurationError,
    LLMError,
    LLMMessage,
    LLMTimeoutError,
    LLMUpstreamError,
)
from app.llm.factory import get_llm_provider
from app.llm.openai_compatible import OpenAICompatibleProvider


def _provider(handler, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        api_key=kwargs.get("api_key", "sk-test"),
        base_url=kwargs.get("base_url", "https://api.example.com/v1"),
        model=kwargs.get("model", "gpt-test"),
        timeout=kwargs.get("timeout", 30.0),
        client=client,
    )


def _body(request):
    return json.loads(request.content.decode("utf-8"))


def _ok_response():
    return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})


def test_missing_api_key_raises_config_error():
    with pytest.raises(LLMConfigurationError):
        OpenAICompatibleProvider(api_key="", base_url="https://x/v1")


def test_missing_base_url_raises_config_error():
    with pytest.raises(LLMConfigurationError):
        OpenAICompatibleProvider(api_key="sk", base_url="")


def test_default_model_used():
    captured = {}

    def handler(request):
        captured["body"] = _body(request)
        return _ok_response()

    provider = _provider(handler, model="gpt-default")
    provider.complete([LLMMessage(role="user", content="hi")])

    assert captured["body"]["model"] == "gpt-default"


def test_single_user_message_converted():
    captured = {}

    def handler(request):
        captured["body"] = _body(request)
        return _ok_response()

    provider = _provider(handler)
    provider.complete([LLMMessage(role="user", content="你好")])

    assert captured["body"]["messages"] == [{"role": "user", "content": "你好"}]
    assert captured["body"]["stream"] is False


def test_multiple_roles_order_preserved():
    captured = {}

    def handler(request):
        captured["body"] = _body(request)
        return _ok_response()

    messages = [
        LLMMessage(role="system", content="sys"),
        LLMMessage(role="user", content="u"),
        LLMMessage(role="assistant", content="a"),
    ]

    provider = _provider(handler)
    provider.complete(messages)

    assert captured["body"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
    ]


def test_normal_response_converted():
    def handler(request):
        return httpx.Response(
            200,
            json={"model": "gpt-test", "choices": [{"message": {"content": "你好呀"}}]},
        )

    provider = _provider(handler)
    resp = provider.complete([LLMMessage(role="user", content="hi")])

    assert resp.content == "你好呀"
    assert resp.model == "gpt-test"


def test_model_override():
    captured = {}

    def handler(request):
        captured["body"] = _body(request)
        return _ok_response()

    provider = _provider(handler, model="gpt-default")
    provider.complete([LLMMessage(role="user", content="hi")], model="gpt-4o")

    assert captured["body"]["model"] == "gpt-4o"


def test_timeout_maps_to_timeout_error():
    def handler(request):
        raise httpx.TimeoutException("timeout")

    provider = _provider(handler)

    with pytest.raises(LLMTimeoutError):
        provider.complete([LLMMessage(role="user", content="hi")])


def test_network_error_mapped():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    provider = _provider(handler)

    with pytest.raises(LLMUpstreamError):
        provider.complete([LLMMessage(role="user", content="hi")])


def test_http_error_mapped():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    provider = _provider(handler)

    with pytest.raises(LLMUpstreamError):
        provider.complete([LLMMessage(role="user", content="hi")])


def test_empty_content_is_error():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    provider = _provider(handler)

    with pytest.raises(LLMError):
        provider.complete([LLMMessage(role="user", content="hi")])


def test_api_key_not_in_exception():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    provider = _provider(handler, api_key="sk-secret-123")

    with pytest.raises(LLMUpstreamError) as exc_info:
        provider.complete([LLMMessage(role="user", content="hi")])

    assert "sk-secret-123" not in str(exc_info.value)


def test_factory_builds_provider(monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "gpt-test")
    monkeypatch.setattr(settings, "LLM_TIMEOUT", 5.0)

    get_llm_provider.cache_clear()
    provider = get_llm_provider()

    assert provider.api_key == "sk-test"
    assert provider.base_url == "https://api.example.com/v1"
    assert provider.model == "gpt-test"
    assert provider.timeout == 5.0

    get_llm_provider.cache_clear()
