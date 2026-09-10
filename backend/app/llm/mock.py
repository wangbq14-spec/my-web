"""Offline mock LLM provider for E2E flows and capacity baselines.

Enabled only when ``LLM_PROVIDER_LABEL=mock`` is explicitly configured.
Returns deterministic canned responses with real usage tokens so billing and
usage analytics still exercise their real code paths. Never reachable in a
normal deployment.
"""

import time

from app.llm.base import (
    ImagePart,
    LLMChunk,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMUsage,
)

_MOCK_TOKENS = 24


class MockLLMProvider(LLMProvider):
    """Deterministic offline provider: canned answers, no network I/O."""

    def __init__(self, model: str = "mock-model", provider: str = "mock",
                 latency_ms: int = 0) -> None:
        self._model = model
        self._provider = provider
        self._latency = latency_ms / 1000

    def _answer(self, messages, model) -> str:
        if self._latency:
            time.sleep(self._latency)
        has_image = any(
            isinstance(part, ImagePart)
            for message in messages
            for part in (message.content_parts or [])
        )
        last_user = next((m for m in reversed(messages) if m.role == "user"), None)
        snippet = (last_user.content or "")[:60].strip() if last_user else ""
        if has_image:
            return f"[mock-vision] 已收到图片与问题：“{snippet}”。（离线模拟：已分析图片内容）"
        return f"[mock] 已收到：“{snippet}”。（离线模拟回答，仅供测试与容量基线使用）"

    def complete(self, messages, *, model=None, tools=None) -> LLMResponse:
        body = self._answer(messages, model)
        return LLMResponse(
            content=body,
            model=model or self._model,
            usage=LLMUsage(prompt_tokens=_MOCK_TOKENS, completion_tokens=_MOCK_TOKENS,
                           total_tokens=_MOCK_TOKENS * 2),
            provider=self._provider,
        )

    def stream(self, messages, *, model=None, tools=None):
        body = self._answer(messages, model)
        if body:
            yield LLMChunk(content=body, model=model or self._model)
        yield LLMChunk(
            content=None,
            model=model or self._model,
            usage=LLMUsage(prompt_tokens=_MOCK_TOKENS, completion_tokens=_MOCK_TOKENS,
                           total_tokens=_MOCK_TOKENS * 2),
        )
