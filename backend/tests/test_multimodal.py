import base64
from types import SimpleNamespace

import pytest

from app.llm.base import ImagePart, TextPart, LLMMessage, LLMError, LLMImageError
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.registry import ModelRegistry, VisionNotSupportedError
from app.core.config import settings


def config(**kwargs):
    values = dict(LLM_MODEL="text", LLM_FAST_MODEL="fast", LLM_STANDARD_MODEL="standard",
                  LLM_REASONING_MODEL="reason", LLM_PROVIDER_LABEL="openai_compatible",
                  VISION_MODEL="vision", VISION_MODEL_TIER="standard", TAOTOKEN_VISION_MODEL="")
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_capability_routing():
    registry = ModelRegistry(config())
    assert registry.resolve_for(capability="text", tier="standard")[1] == "standard"
    assert registry.resolve_for(capability="vision", tier="standard")[1] == "vision"
    with pytest.raises(VisionNotSupportedError, match="当前模型不支持图片理解，请切换支持图片的模型"):
        registry.resolve_for(capability="vision", tier="fast")
    assert registry.capabilities("standard")["vision"] is True
    assert registry.capabilities("fast")["vision"] is False


def test_taotoken_configuration():
    registry = ModelRegistry(config(VISION_MODEL="", TAOTOKEN_VISION_MODEL="configured-only"))
    assert registry.resolve_for(capability="vision", tier="standard") == ("taotoken", "configured-only")


def test_adapter_serializes_local_image(tmp_path):
    raw = b"\x89PNG\r\n\x1a\nexample"
    path = tmp_path / "image.png"
    path.write_bytes(raw)
    message = LLMMessage(role="user", content="describe", content_parts=[
        TextPart(text="describe"), ImagePart(data_url_or_path=str(path), mime_type="image/png")])
    result = OpenAICompatibleProvider._serialize_message(message)
    assert result == {"role": "user", "content": [
        {"type": "text", "text": "describe"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(raw).decode()}}]}
    assert str(path) not in str(result)


def test_adapter_rejects_oversized_image(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CHAT_IMAGE_SIZE", 3)
    path = tmp_path / "image.png"
    path.write_bytes(b"1234")
    with pytest.raises(LLMError, match="图片超过"):
        OpenAICompatibleProvider._serialize_message(LLMMessage(role="user", content_parts=[
            ImagePart(data_url_or_path=str(path), mime_type="image/png")]))


def test_text_serialization_unchanged():
    assert OpenAICompatibleProvider._serialize_message(LLMMessage(role="user", content="hello")) == {
        "role": "user", "content": "hello"}


def test_adapter_rejects_remote_url_and_invalid_base64():
    for value in ("https://example.com/private.png", "data:image/png;base64,%%%"):
        with pytest.raises(LLMError):
            OpenAICompatibleProvider._serialize_message(LLMMessage(role="user", content_parts=[
                ImagePart(data_url_or_path=value, mime_type="image/png")]))


def test_adapter_image_errors_carry_distinct_codes(tmp_path, monkeypatch):
    """发送阶段图片错误必须携带可区分的 code，避免被前端归为通用失败。"""
    monkeypatch.setattr(settings, "MAX_CHAT_IMAGE_SIZE", 3)

    oversized = tmp_path / "big.png"
    oversized.write_bytes(b"1234")
    with pytest.raises(LLMImageError) as exc:
        OpenAICompatibleProvider._serialize_message(LLMMessage(role="user", content_parts=[
            ImagePart(data_url_or_path=str(oversized), mime_type="image/png")]))
    assert exc.value.code == "image_too_large"

    missing = tmp_path / "gone.png"
    with pytest.raises(LLMImageError) as exc:
        OpenAICompatibleProvider._serialize_message(LLMMessage(role="user", content_parts=[
            ImagePart(data_url_or_path=str(missing), mime_type="image/png")]))
    assert exc.value.code == "image_read_failed"

    with pytest.raises(LLMImageError) as exc:
        OpenAICompatibleProvider._serialize_message(LLMMessage(role="user", content_parts=[
            ImagePart(data_url_or_path="data:image/png;base64,%%%", mime_type="image/png")]))
    assert exc.value.code == "image_format"