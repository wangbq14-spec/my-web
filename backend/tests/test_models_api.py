import pytest
from pydantic import ValidationError

from app.api.routes import models
from app.schemas.agent import AgentRequest
from app.schemas.chat import ChatRequest


def test_models_endpoint_returns_product_tiers(client, monkeypatch):
    expected = [{"tier": "auto", "name": "自动", "description": "自动选择默认模型"}]

    class Registry:
        def tiers(self):
            return expected

    monkeypatch.setattr(models, "get_model_registry", lambda: Registry())

    response = client.get("/api/models")

    assert response.status_code == 200
    assert response.json() == expected


def test_model_tier_defaults_to_auto():
    assert ChatRequest(content="hello").model_tier == "auto"
    assert AgentRequest(content="hello").model_tier == "auto"


@pytest.mark.parametrize("content,attachment_ids", [
    ("hello", []),          # text only
    ("hello", [1]),         # text + image
    ("", [1]),              # image only (empty content)
    ("   ", [1]),           # image only (whitespace content)
])
def test_chat_request_accepts_text_or_image(content, attachment_ids):
    request = ChatRequest(content=content, attachment_ids=attachment_ids)
    assert request.content == content
    assert request.attachment_ids == attachment_ids


@pytest.mark.parametrize("content,attachment_ids", [
    ("", []),               # completely empty message
    ("   ", []),            # whitespace-only message
])
def test_chat_request_rejects_empty_message(content, attachment_ids):
    with pytest.raises(ValidationError):
        ChatRequest(content=content, attachment_ids=attachment_ids)
