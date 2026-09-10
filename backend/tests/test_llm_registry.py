import pytest

from app.llm.base import LLMConfigurationError
from app.llm.registry import ModelRegistry, VisionNotSupportedError, resolve_model


def _settings(**overrides):
    base = dict(
        LLM_MODEL="default-model",
        LLM_FAST_MODEL="",
        LLM_STANDARD_MODEL="",
        LLM_REASONING_MODEL="",
        LLM_PROVIDER_LABEL="openai_compatible",
        VISION_MODEL="",
        VISION_MODEL_TIER="standard",
        TAOTOKEN_VISION_MODEL="",
    )
    base.update(overrides)

    class Settings:
        pass

    s = Settings()
    for key, value in base.items():
        setattr(s, key, value)
    return s


def test_registry_resolves_configured_tiers_and_falls_back_to_default():
    class Settings:
        LLM_MODEL = "default-model"
        LLM_FAST_MODEL = "fast-model"
        LLM_STANDARD_MODEL = ""
        LLM_REASONING_MODEL = "reasoning-model"
        LLM_PROVIDER_LABEL = "openai_compatible"

    registry = ModelRegistry(Settings())

    assert registry.resolve(None) == ("openai_compatible", "default-model")
    assert registry.resolve("auto") == ("openai_compatible", "default-model")
    assert registry.resolve("fast") == ("openai_compatible", "fast-model")
    assert registry.resolve("standard") == ("openai_compatible", "default-model")
    assert registry.resolve("reasoning") == ("openai_compatible", "reasoning-model")


def test_registry_rejects_unknown_tier():
    class Settings:
        LLM_MODEL = "default-model"
        LLM_FAST_MODEL = ""
        LLM_STANDARD_MODEL = ""
        LLM_REASONING_MODEL = ""
        LLM_PROVIDER_LABEL = "openai_compatible"

    with pytest.raises(LLMConfigurationError):
        ModelRegistry(Settings()).resolve("unsupported")


def test_registry_exposes_product_tier_metadata():
    class Settings:
        LLM_MODEL = "default-model"
        LLM_FAST_MODEL = ""
        LLM_STANDARD_MODEL = ""
        LLM_REASONING_MODEL = ""
        LLM_PROVIDER_LABEL = "openai_compatible"

    assert ModelRegistry(Settings()).tiers() == [
        {"tier": "auto", "name": "自动", "description": "自动选择默认模型"},
        {"tier": "fast", "name": "快速", "description": "优先响应速度"},
        {"tier": "standard", "name": "均衡", "description": "兼顾速度与质量"},
        {"tier": "reasoning", "name": "深度思考", "description": "优先复杂推理能力"},
    ]


def test_vision_target_prefers_taotoken_when_configured():
    s = _settings(VISION_MODEL="Qwen/Qwen2.5-VL-32B-Instruct",
                  TAOTOKEN_VISION_MODEL="kimi-k3")
    assert ModelRegistry(s)._vision_target() == ("taotoken", "kimi-k3")


def test_vision_target_falls_back_to_generic_vision_block():
    s = _settings(VISION_MODEL="Qwen/Qwen2.5-VL-32B-Instruct")
    assert ModelRegistry(s)._vision_target() == ("openai_compatible", "Qwen/Qwen2.5-VL-32B-Instruct")


def test_vision_capability_resolves_taotoken_and_is_tier_scoped():
    s = _settings(TAOTOKEN_VISION_MODEL="kimi-k3", VISION_MODEL_TIER="standard")
    registry = ModelRegistry(s)
    assert registry.capabilities("standard")["vision"] is True
    assert registry.capabilities("fast")["vision"] is False
    assert registry.resolve_for(capability="vision", tier="standard") == ("taotoken", "kimi-k3")


def test_vision_resolve_raises_when_no_vision_model_configured():
    registry = ModelRegistry(_settings())
    with pytest.raises(VisionNotSupportedError):
        registry.resolve_for(capability="vision", tier="standard")


def test_resolve_model_ignores_client_explicit_model(monkeypatch):
    # P1-3: an arbitrary client-supplied model must never be forwarded verbatim;
    # the server always resolves from the product tier.
    from app.llm import registry as registry_module

    monkeypatch.setattr(
        registry_module,
        "get_model_registry",
        lambda: ModelRegistry(_settings(LLM_MODEL="server-default")),
    )
    assert registry_module.resolve_model(None, "attacker-chosen") == "server-default"
    assert registry_module.resolve_model("auto", "attacker-chosen") == "server-default"
    assert registry_module.resolve_model("fast", "attacker-chosen") == "server-default"
