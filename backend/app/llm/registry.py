from functools import lru_cache
from typing import Literal

from app.core.config import settings
from app.llm.base import LLMConfigurationError

ModelTier = Literal["auto", "fast", "standard", "reasoning"]


class VisionNotSupportedError(LLMConfigurationError):
    def __init__(self):
        super().__init__("当前模型不支持图片理解，请切换支持图片的模型")


class ModelRegistry:
    """Resolve product-facing model tiers without exposing provider config."""

    _TIER_METADATA = (
        ("auto", "自动", "自动选择默认模型"),
        ("fast", "快速", "优先响应速度"),
        ("standard", "均衡", "兼顾速度与质量"),
        ("reasoning", "深度思考", "优先复杂推理能力"),
    )

    def __init__(self, config=settings) -> None:
        self._config = config

    def resolve(self, tier: str | None) -> tuple[str, str]:
        if tier is None or tier == "auto":
            model = self._config.LLM_MODEL
        elif tier == "fast":
            model = self._config.LLM_FAST_MODEL or self._config.LLM_MODEL
        elif tier == "standard":
            model = self._config.LLM_STANDARD_MODEL or self._config.LLM_MODEL
        elif tier == "reasoning":
            model = self._config.LLM_REASONING_MODEL or self._config.LLM_MODEL
        else:
            raise LLMConfigurationError(f"未知模型档位: {tier}")
        if not model:
            raise LLMConfigurationError("LLM_MODEL 未配置")
        return self._config.LLM_PROVIDER_LABEL, model

    def _vision_target(self) -> tuple[str, str]:
        if getattr(self._config, "LLM_PROVIDER_LABEL", "") == "mock":
            return "mock", self._config.LLM_MODEL or "mock-vision-model"
        # Prefer an explicitly configured Taotoken vision model (OpenAI-compatible
        # multimodal endpoint, e.g. kimi-k3); fall back to the generic VISION_* block.
        taotoken_model = getattr(self._config, "TAOTOKEN_VISION_MODEL", "")
        if taotoken_model:
            return "taotoken", taotoken_model
        model = getattr(self._config, "VISION_MODEL", "")
        if model:
            return self._config.LLM_PROVIDER_LABEL, model
        return "taotoken", ""

    def capabilities(self, tier: str | None) -> dict[str, bool]:
        effective_tier = tier or "auto"
        if effective_tier not in {entry[0] for entry in self._TIER_METADATA}:
            raise LLMConfigurationError(f"未知模型档位: {tier}")
        _, model = self._vision_target()
        return {
            "text": True,
            "vision": bool(model) and effective_tier == getattr(
                self._config, "VISION_MODEL_TIER", "standard"),
            # Tools/reasoning are explicit product-tier capabilities, not guessed
            # from provider model names. Vision requests currently do not use tools.
            "tools": effective_tier != "reasoning",
            "reasoning": effective_tier == "reasoning",
        }

    def resolve_for(self, *, capability: str = "text", tier: str | None = "auto") -> tuple[str, str]:
        capabilities = self.capabilities(tier)
        if not capabilities.get(capability, False):
            if capability == "vision":
                raise VisionNotSupportedError()
            raise LLMConfigurationError(f"当前模型不支持能力: {capability}")
        if capability == "vision":
            return self._vision_target()
        return self.resolve(tier)

    def models(self) -> list[dict]:
        """Capability metadata without changing the legacy tiers() API."""
        return [dict(entry, capabilities=self.capabilities(entry["tier"]))
                for entry in self.tiers()]

    def tiers(self) -> list[dict[str, str]]:
        return [
            {"tier": tier, "name": name, "description": description}
            for tier, name, description in self._TIER_METADATA
        ]


@lru_cache
def get_model_registry() -> ModelRegistry:
    return ModelRegistry()


def resolve_model(tier: ModelTier | None, explicit_model: str | None = None) -> str:
    """Resolve the provider model server-authoritatively from the product tier.

    The client-supplied ``explicit_model`` (conversation.model) is deliberately
    ignored: it was an arbitrary string that could be forwarded to the provider
    verbatim under tier=auto, enabling cost escalation / upstream 400s. The
    server always resolves from the tier so the model is never client-chosen.
    """
    return get_model_registry().resolve(tier or "auto")[1]
