import json

import httpx
import pytest

from app.llm.base import LLMError, LLMMessage, LLMTimeoutError
from app.llm.openai_compatible import OpenAICompatibleProvider


def _provider(handler):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        api_key="sk-test",
        base_url="https://x/v1",
        model="gpt-test",
        client=client,
    )


def test_stream_parses_chunks_and_model():
    sse = (
        'data: {"choices":[{"delta":{"content":"你"}}],"model":"gpt-test"}\n\n'
        'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, content=sse.encode("utf-8"))

    provider = _provider(handler)
    chunks = list(provider.stream([LLMMessage(role="user", content="hi")]))

    assert [c.content for c in chunks] == ["你", "好"]
    assert chunks[0].model == "gpt-test"


def test_stream_skips_empty_delta():
    sse = (
        'data: {"choices":[{"delta":{}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        return httpx.Response(200, content=sse.encode("utf-8"))

    provider = _provider(handler)
    chunks = list(provider.stream([LLMMessage(role="user", content="hi")]))

    assert [c.content for c in chunks] == ["好"]


def test_stream_requests_and_emits_usage():
    captured = {}
    sse = (
        'data: {"choices":[{"delta":{"content":"ok"}}],"model":"gpt-test"}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request):
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, content=sse.encode("utf-8"))

    chunks = list(_provider(handler).stream([LLMMessage(role="user", content="hi")]))

    assert captured["body"]["stream_options"] == {"include_usage": True}
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.total_tokens == 5


def test_stream_retries_without_usage_option_after_bad_request():
    payloads = []
    sse = 'data: {"choices":[{"delta":{"content":"ok"}}]}\n\ndata: [DONE]\n\n'

    def handler(request):
        payloads.append(json.loads(request.content.decode("utf-8")))
        if len(payloads) == 1:
            return httpx.Response(400, json={"error": "unsupported stream_options"})
        return httpx.Response(200, content=sse.encode("utf-8"))

    chunks = list(_provider(handler).stream([LLMMessage(role="user", content="hi")]))

    assert [chunk.content for chunk in chunks] == ["ok"]
    assert "stream_options" in payloads[0]
    assert "stream_options" not in payloads[1]


def test_stream_malformed_json_raises():
    sse = "data: {invalid json}\n\n"

    def handler(request):
        return httpx.Response(200, content=sse.encode("utf-8"))

    provider = _provider(handler)

    with pytest.raises(LLMError):
        list(provider.stream([LLMMessage(role="user", content="hi")]))


def test_stream_timeout_maps():
    def handler(request):
        raise httpx.TimeoutException("timeout")

    provider = _provider(handler)

    with pytest.raises(LLMTimeoutError):
        list(provider.stream([LLMMessage(role="user", content="hi")]))
