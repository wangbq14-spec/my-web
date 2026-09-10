import base64
import binascii
import json
from pathlib import Path

from app.core.config import settings
from collections.abc import Iterator, Sequence

import httpx

from app.llm.base import (
    ImagePart,
    TextPart,
    LLMChunk,
    LLMConfigurationError,
    LLMError,
    LLMImageError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMTimeoutError,
    LLMToolCall,
    LLMUpstreamError,
    LLMUsage,
)


# Minimal instruction injected only into the provider request when a message is
# image-only. It is never persisted as user text and never written back to the
# conversation.
_VISION_DEFAULT_INSTRUCTION = "请描述并回应这张图片。"


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

    @staticmethod
    def _image_url(part: ImagePart) -> str:
        value = part.data_url_or_path
        max_bytes = settings.MAX_CHAT_IMAGE_SIZE
        max_encoded = settings.MAX_CHAT_IMAGE_BASE64_SIZE
        prefix = f"data:{part.mime_type};base64,"
        if value.startswith("data:"):
            if not value.startswith(prefix):
                raise LLMImageError("image_format", "图片格式不支持，仅支持 JPEG、PNG、WebP")
            encoded = value[len(prefix):]
            if len(encoded) > max_encoded:
                raise LLMImageError("image_too_large", "图片超过大小限制，请压缩后重新上传")
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                raise LLMImageError("image_format", "图片格式不支持，仅支持 JPEG、PNG、WebP") from None
        else:
            if "://" in value:
                raise LLMImageError("image_format", "不支持远程图片地址")
            try:
                # Bounded read, including when a file grows after upload.
                with Path(value).open("rb") as source:
                    raw = source.read(max_bytes + 1)
            except (OSError, ValueError):
                raise LLMImageError("image_read_failed", "图片读取失败，请重新上传") from None
            if len(raw) > max_bytes:
                raise LLMImageError("image_too_large", "图片超过大小限制，请压缩后重新上传")
            encoded = base64.b64encode(raw).decode("ascii")
        if not raw:
            raise LLMImageError("image_read_failed", "图片读取失败，请重新上传")
        if len(raw) > max_bytes or len(encoded) > max_encoded:
            raise LLMImageError("image_too_large", "图片超过大小限制，请压缩后重新上传")
        return prefix + encoded

    @staticmethod
    def _serialize_message(message: LLMMessage) -> dict:
        serialized = {"role": message.role, "content": message.content}
        if message.content_parts is not None:
            parts = []
            if message.content:
                parts.append({"type": "text", "text": message.content})
            for part in message.content_parts:
                if isinstance(part, TextPart):
                    if not message.content:
                        parts.append({"type": "text", "text": part.text})
                elif isinstance(part, ImagePart):
                    parts.append({"type": "image_url", "image_url": {
                        "url": OpenAICompatibleProvider._image_url(part)}})
            if parts and not any(item.get("type") == "text" for item in parts):
                # Some OpenAI-compatible vision endpoints require a text part
                # alongside images; inject a minimal internal instruction.
                parts.insert(0, {"type": "text", "text": _VISION_DEFAULT_INSTRUCTION})
            serialized["content"] = parts
        if message.tool_calls is not None:
            serialized["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    },
                }
                for tool_call in message.tool_calls
            ]
        if message.tool_call_id is not None:
            serialized["tool_call_id"] = message.tool_call_id
        if message.name is not None:
            serialized["name"] = message.name
        return serialized

    @staticmethod
    def _parse_tool_calls(raw_tool_calls: object) -> list[LLMToolCall] | None:
        if raw_tool_calls is None:
            return None
        if not isinstance(raw_tool_calls, list):
            raise LLMError("上游返回格式异常")

        tool_calls: list[LLMToolCall] = []
        for raw_tool_call in raw_tool_calls:
            if not isinstance(raw_tool_call, dict):
                raise LLMError("上游返回格式异常")
            if raw_tool_call.get("type") != "function":
                raise LLMError("上游返回格式异常")

            tool_call_id = raw_tool_call.get("id")
            function = raw_tool_call.get("function")
            if (
                not isinstance(tool_call_id, str)
                or not isinstance(function, dict)
                or not isinstance(function.get("name"), str)
                or not isinstance(function.get("arguments"), str)
            ):
                raise LLMError("上游返回格式异常")

            tool_calls.append(
                LLMToolCall(
                    id=tool_call_id,
                    name=function["name"],
                    arguments=function["arguments"],
                )
            )
        return tool_calls

    @staticmethod
    def _parse_usage(raw_usage: object) -> LLMUsage | None:
        if raw_usage is None:
            return None
        if not isinstance(raw_usage, dict):
            raise LLMError("上游返回格式异常")
        values: dict[str, int] = {}
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = raw_usage.get(field)
            if value is not None:
                if not isinstance(value, int) or isinstance(value, bool):
                    raise LLMError("上游返回格式异常")
                values[field] = value
        return LLMUsage(**values)

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        effective_model = model or self.model
        if not effective_model:
            raise LLMConfigurationError("LLM_MODEL 未配置")

        payload = {
            "model": effective_model,
            "messages": [self._serialize_message(message) for message in messages],
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
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
            message = data["choices"][0]["message"]
            if not isinstance(message, dict):
                raise TypeError
            content = message.get("content")
            tool_calls = self._parse_tool_calls(message.get("tool_calls"))
            usage = self._parse_usage(data.get("usage"))
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("上游返回格式异常") from exc

        if isinstance(content, str):
            text = content
        elif content is None:
            text = ""
        else:
            raise LLMError("上游返回格式异常")

        if not text.strip() and not tool_calls:
            raise LLMError("上游返回空内容")

        return LLMResponse(
            content=content,
            tool_calls=tool_calls or None,
            model=data.get("model") or effective_model,
            usage=usage,
            provider="openai_compatible",
        )

    def stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> Iterator[LLMChunk]:
        yield from self._stream(messages, model=model, tools=tools, include_usage=True)

    def _stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
        include_usage: bool,
    ) -> Iterator[LLMChunk]:
        effective_model = model or self.model
        if not effective_model:
            raise LLMConfigurationError("LLM_MODEL 未配置")

        payload = {
            "model": effective_model,
            "messages": [self._serialize_message(message) for message in messages],
            "stream": True,
        }
        if include_usage:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = tools
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        use_tools = bool(tools)
        tool_call_parts: dict[int, dict[str, object]] = {}
        last_model: str | None = None
        saw_done = False

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
                        saw_done = True
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise LLMError("上游流式数据格式异常") from exc

                    if not isinstance(obj, dict):
                        raise LLMError("上游流式数据格式异常")
                    usage = self._parse_usage(obj.get("usage"))
                    choices = obj.get("choices")
                    if not isinstance(choices, list):
                        raise LLMError("上游流式数据格式异常")
                    if not choices:
                        if usage is not None:
                            yield LLMChunk(usage=usage, model=obj.get("model"))
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        raise LLMError("上游流式数据格式异常")
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        raise LLMError("上游流式数据格式异常")

                    chunk_model = obj.get("model")
                    if use_tools and isinstance(chunk_model, str) and chunk_model:
                        last_model = chunk_model
                    content = delta.get("content")
                    if content:
                        if not isinstance(content, str):
                            raise LLMError("上游流式数据格式异常")
                        yield LLMChunk(content=content, model=chunk_model)

                    if usage is not None:
                        yield LLMChunk(usage=usage, model=chunk_model)

                    if use_tools and "tool_calls" in delta:
                        raw_tool_calls = delta["tool_calls"]
                        if not isinstance(raw_tool_calls, list):
                            raise LLMError("上游流式数据格式异常")
                        for raw_tool_call in raw_tool_calls:
                            if not isinstance(raw_tool_call, dict):
                                raise LLMError("上游流式数据格式异常")
                            index = raw_tool_call.get("index")
                            function = raw_tool_call.get("function")
                            tool_call_type = raw_tool_call.get("type")
                            if (
                                not isinstance(index, int)
                                or isinstance(index, bool)
                                or index < 0
                                or (
                                    tool_call_type is not None
                                    and tool_call_type != "function"
                                )
                                or (function is not None and not isinstance(function, dict))
                            ):
                                raise LLMError("上游流式数据格式异常")

                            part = tool_call_parts.setdefault(
                                index, {"id": None, "name": None, "arguments": []}
                            )
                            tool_call_id = raw_tool_call.get("id")
                            if tool_call_id is not None:
                                if not isinstance(tool_call_id, str):
                                    raise LLMError("上游流式数据格式异常")
                                if part["id"] is None:
                                    part["id"] = tool_call_id

                            if function is not None:
                                name = function.get("name")
                                arguments = function.get("arguments")
                                if name is not None:
                                    if not isinstance(name, str):
                                        raise LLMError("上游流式数据格式异常")
                                    if part["name"] is None:
                                        part["name"] = name
                                if arguments is not None:
                                    if not isinstance(arguments, str):
                                        raise LLMError("上游流式数据格式异常")
                                    part["arguments"].append(arguments)

                if use_tools and saw_done and tool_call_parts:
                    tool_calls: list[LLMToolCall] = []
                    for _, part in sorted(tool_call_parts.items()):
                        tool_call_id = part["id"]
                        name = part["name"]
                        arguments = part["arguments"]
                        if (
                            not isinstance(tool_call_id, str)
                            or not isinstance(name, str)
                            or not isinstance(arguments, list)
                            or not all(isinstance(argument, str) for argument in arguments)
                        ):
                            raise LLMError("上游流式数据格式异常")
                        tool_calls.append(
                            LLMToolCall(
                                id=tool_call_id,
                                name=name,
                                arguments="".join(arguments),
                            )
                        )
                    yield LLMChunk(tool_calls=tool_calls, model=last_model)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("LLM 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            if include_usage and exc.response.status_code == 400:
                yield from self._stream(
                    messages, model=model, tools=tools, include_usage=False
                )
                return
            raise LLMUpstreamError(
                f"上游服务错误（HTTP {exc.response.status_code}）"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMUpstreamError("网络连接失败") from exc
