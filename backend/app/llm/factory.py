from functools import lru_cache

from app.core.config import settings
from app.llm.mock import MockLLMProvider
from app.llm.openai_compatible import OpenAICompatibleProvider


@lru_cache
def get_llm_provider():
    if settings.LLM_PROVIDER_LABEL == "mock":
        return MockLLMProvider(model=settings.LLM_MODEL or "mock-model", provider="mock")
    return OpenAICompatibleProvider(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        timeout=settings.LLM_TIMEOUT,
    )


@lru_cache
def get_vision_provider(provider_label: str):
    if provider_label == "mock":
        return MockLLMProvider(
            model=settings.VISION_MODEL or settings.LLM_MODEL or "mock-vision-model",
            provider="mock",
        )
    if provider_label == "taotoken":
        return OpenAICompatibleProvider(
            api_key=settings.TAOTOKEN_API_KEY,
            base_url=settings.TAOTOKEN_BASE_URL,
            model=settings.TAOTOKEN_VISION_MODEL,
            timeout=settings.VISION_TIMEOUT,
        )
    if settings.VISION_API_KEY and settings.VISION_BASE_URL:
        return OpenAICompatibleProvider(
            api_key=settings.VISION_API_KEY,
            base_url=settings.VISION_BASE_URL,
            model=settings.VISION_MODEL,
            timeout=settings.VISION_TIMEOUT,
        )
    return get_llm_provider()
