from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from typing import Literal

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    content: str
    model: str | None = None


class LLMChunk(BaseModel):
    content: str
    model: str | None = None


class LLMError(Exception):
    """LLM 调用统一异常基类。"""


class LLMConfigurationError(LLMError):
    """LLM 配置缺失或错误。"""


class LLMTimeoutError(LLMError):
    """LLM 请求超时。"""


class LLMUpstreamError(LLMError):
    """上游服务网络/HTTP 错误。"""


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    def stream(
        self,
        messages: Sequence[LLMMessage],
        *,
        model: str | None = None,
    ) -> Iterator[LLMChunk]:
        raise NotImplementedError
