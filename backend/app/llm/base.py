from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    # Never include image data or local storage paths in repr/validation errors.
    model_config = ConfigDict(hide_input_in_errors=True)
    type: Literal["image"] = "image"
    data_url_or_path: str = Field(repr=False)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]


LLMContentPart = TextPart | ImagePart


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    content_parts: list[LLMContentPart] | None = Field(default=None, repr=False)
    tool_calls: list["LLMToolCall"] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class LLMToolCall(BaseModel):
    id: str
    name: str
    arguments: str


class LLMUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[LLMToolCall] | None = None
    model: str | None = None
    usage: LLMUsage | None = None
    provider: str | None = None


class LLMChunk(BaseModel):
    content: str | None = None
    tool_calls: list[LLMToolCall] | None = None
    model: str | None = None
    usage: LLMUsage | None = None


class LLMError(Exception):
    """LLM 调用统一异常基类。"""


class LLMConfigurationError(LLMError):
    """LLM 配置缺失或错误。"""


class LLMTimeoutError(LLMError):
    """LLM 请求超时。"""


class LLMUpstreamError(LLMError):
    """上游服务网络/HTTP 错误。"""


class LLMImageError(LLMError):
    """图片读取/序列化失败，携带机器可读错误码供前端区分错误类型。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    def stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> Iterator[LLMChunk]:
        raise NotImplementedError
