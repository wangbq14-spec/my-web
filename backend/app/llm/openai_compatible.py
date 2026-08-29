import json
from collections.abc import Iterator, Sequence

import httpx

from app.llm.base import (
    LLMChunk,
    LLMConfigurationError,
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMTimeoutError,
    LLMUpstreamError,
)


class OpenAICompatibleProvider(LLMProvider):
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
            raise LLMConfigurationError("LLM_API_KEY 未配置")
        if not base_url:
            raise LLMConfigurationError("LLM_BASE_URL 未配置")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = client if client is not None else httpx.Client(timeout=timeout)

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
    ) -> LLMResponse:
        effective_model = model or self.model
        if not effective_model:
            raise LLMConfigurationError("LLM_MODEL 未配置")

        payload = {
            "model": effective_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        try:
            response = self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("LLM 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMUpstreamError(
                f"上游服务错误（HTTP {exc.response.status_code}）"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMUpstreamError("网络连接失败") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("上游返回格式异常") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("上游返回格式异常") from exc

        if isinstance(content, str):
            text = content
        elif content is None:
            text = ""
        else:
            raise LLMError("上游返回格式异常")

        if not text.strip():
            raise LLMError("上游返回空内容")

        return LLMResponse(
            content=text,
            model=data.get("model") or effective_model,
        )

    def stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
    ) -> Iterator[LLMChunk]:
        effective_model = model or self.model
        if not effective_model:
            raise LLMConfigurationError("LLM_MODEL 未配置")

        payload = {
            "model": effective_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        try:
            with self._client.stream(
                "POST", url, json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise LLMError("上游流式数据格式异常") from exc

                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield LLMChunk(content=content, model=obj.get("model"))
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("LLM 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMUpstreamError(
                f"上游服务错误（HTTP {exc.response.status_code}）"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMUpstreamError("网络连接失败") from exc


