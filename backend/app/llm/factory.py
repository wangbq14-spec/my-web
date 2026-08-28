from functools import lru_cache

from app.core.config import settings
from app.llm.openai_compatible import OpenAICompatibleProvider


@lru_cache
def get_llm_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        timeout=settings.LLM_TIMEOUT,
    )
