import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from starlette.datastructures import Headers

from app.api.routes.auth import get_current_user
from app.core.config import settings
from app.llm.base import ImagePart, LLMChunk, LLMImageError, LLMResponse, LLMUpstreamError, LLMUsage, TextPart
from app.main import app
from app.models.beta import MessageAttachment
from app.models.billing import UsageRecord
from app.models.message import Message
from app.models.user import User
from app.schemas.conversation import ConversationCreate
from app.services import chat
from app.services.attachments import upload_attachment
from app.services.billing import InsufficientCredits, get_balance, grant_credit
from app.services.conversation import create_conversation


class VisionProvider:
    def __init__(self):
        self.calls = []
        self.usage = None
        self.error = False

    def complete(self, messages, *, model=None):
        self.calls.append((messages, model))
        if self.error:
            raise LLMUpstreamError("provider failed")
        return LLMResponse(content="image answer", model=model, usage=self.usage)

    def stream(self, messages, *, model=None):
        response = self.complete(messages, model=model)
        yield LLMChunk(content=response.content)
        yield LLMChunk(model="actual-vision", usage=response.usage)


@pytest.fixture
def setup_vision(db, monkeypatch):
    monkeypatch.setattr(settings, "VISION_MODEL", "vision-model")
    # Isolate from the real .env so the generic VISION_* path is under test
    # regardless of any configured TAOTOKEN_VISION_MODEL.
    monkeypatch.setattr(settings, "TAOTOKEN_VISION_MODEL", "")
    monkeypatch.setattr(settings, "VISION_MODEL_TIER", "standard")
    monkeypatch.setattr(settings, "VISION_BASE_CREDIT_COST", 0)
    user = User(email="vision@example.com", username="vision", hashed_password="x")
    db.add(user)
    db.flush()
    grant_credit(db, user.id, 100, "test")
    conversation = create_conversation(db, user.id, ConversationCreate(title="Vision"))
    upload = UploadFile(filename="test.png", file=BytesIO(b"\x89PNG\r\n\x1a\ntest"),
                        headers=Headers({"content-type": "image/png"}))
    attachment = asyncio.run(upload_attachment(db, user.id, upload))
    db.commit()
    provider = VisionProvider()
    monkeypatch.setattr(chat, "get_vision_provider", lambda label: provider)
    return user, conversation, attachment, provider


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("floor", [0, 7])
@pytest.mark.parametrize("usage", [None, LLMUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)])
def test_vision_binding_and_billing(db, monkeypatch, setup_vision, streaming, floor, usage):
    user, conversation, attachment, provider = setup_vision
    provider.usage = usage
    monkeypatch.setattr(settings, "VISION_BASE_CREDIT_COST", floor)
    if streaming:
        events = list(chat.stream_chat_message(db, user.id, conversation.id, "describe",
                      model_tier="standard", attachment_ids=[attachment.id]))
        assert events[-1].type == "done"
        assert events[-1].model == "actual-vision"
    else:
        result = chat.send_chat_message(db, user.id, conversation.id, "describe",
                      model_tier="standard", attachment_ids=[attachment.id])
        assert result.assistant_message.model == "vision-model"
    db.refresh(attachment)
    assert attachment.message_id is not None
    assert attachment.conversation_id == conversation.id
    assert any(isinstance(part, ImagePart) for part in provider.calls[0][0][-1].content_parts)
    assert provider.calls[0][1] == "vision-model"
    record = db.scalar(select(UsageRecord))
    assert record.credits_charged == max(1, floor)
    assert record.model_tier == "standard"
    assert record.provider == settings.LLM_PROVIDER_LABEL
    assert record.prompt_tokens == (1 if usage else 0)
    assert get_balance(db, user.id)[0] == 100 - max(1, floor)


def test_token_charge_above_floor(db, monkeypatch, setup_vision):
    user, conversation, attachment, provider = setup_vision
    provider.usage = LLMUsage(prompt_tokens=10000, completion_tokens=1000, total_tokens=11000)
    monkeypatch.setattr(settings, "CREDIT_INPUT_RATE", 1.0)
    monkeypatch.setattr(settings, "CREDIT_OUTPUT_RATE", 2.0)
    monkeypatch.setattr(settings, "VISION_BASE_CREDIT_COST", 7)
    chat.send_chat_message(db, user.id, conversation.id, "describe",
                          model_tier="standard", attachment_ids=[attachment.id])
    assert db.scalar(select(UsageRecord)).credits_charged == 12


def test_history_and_regeneration_restore_images(db, setup_vision):
    user, conversation, attachment, provider = setup_vision
    chat.send_chat_message(db, user.id, conversation.id, "describe",
                          model_tier="standard", attachment_ids=[attachment.id])
    list(chat.regenerate_chat_message(db, user.id, conversation.id, model_tier="standard"))
    chat.send_chat_message(db, user.id, conversation.id, "more", model_tier="standard")
    assert len(provider.calls) == 3
    for messages, model in provider.calls:
        assert model == "vision-model"
        assert any(isinstance(part, ImagePart) for m in messages for part in (m.content_parts or []))


@pytest.mark.parametrize("streaming", [False, True])
def test_provider_failure_rolls_back_bindings(db, setup_vision, streaming):
    user, conversation, attachment, provider = setup_vision
    provider.error = True
    with pytest.raises(LLMUpstreamError):
        if streaming:
            list(chat.stream_chat_message(db, user.id, conversation.id, "describe",
                 model_tier="standard", attachment_ids=[attachment.id]))
        else:
            chat.send_chat_message(db, user.id, conversation.id, "describe",
                 model_tier="standard", attachment_ids=[attachment.id])
    db.rollback()
    db.refresh(attachment)
    assert attachment.message_id is None
    assert db.scalars(select(Message)).all() == []
    assert db.scalars(select(UsageRecord)).all() == []
    assert get_balance(db, user.id)[0] == 100


def test_conversation_limit_and_rebinding(db, monkeypatch, setup_vision):
    user, conversation, attachment, provider = setup_vision
    chat.send_chat_message(db, user.id, conversation.id, "describe",
                          model_tier="standard", attachment_ids=[attachment.id])
    with pytest.raises(HTTPException):
        chat.send_chat_message(db, user.id, conversation.id, "again",
                              model_tier="standard", attachment_ids=[attachment.id])
    monkeypatch.setattr(settings, "MAX_CHAT_IMAGES_PER_CONVERSATION", 1)
    upload = UploadFile(filename="second.png", file=BytesIO(b"\x89PNG\r\n\x1a\ntest"),
                        headers=Headers({"content-type": "image/png"}))
    second = asyncio.run(upload_attachment(db, user.id, upload))
    with pytest.raises(HTTPException, match="每会话"):
        chat.send_chat_message(db, user.id, conversation.id, "again",
                              model_tier="standard", attachment_ids=[second.id])


@pytest.mark.parametrize("suffix", ["/chat", "/chat/stream"])
@pytest.mark.parametrize("case,expected", [("success", 201), ("unsupported", 400),
                                           ("balance", 402), ("failure", 502), ("ownership", 404)])
def test_chat_api_attachment_forwarding(client, db, monkeypatch, setup_vision, suffix, case, expected):
    user, conversation, attachment, provider = setup_vision
    app.dependency_overrides[get_current_user] = lambda: user
    if case == "balance":
        monkeypatch.setattr(settings, "VISION_BASE_CREDIT_COST", 101)
    if case == "unsupported":
        # No vision provider configured at all -> the documented error UX.
        monkeypatch.setattr(settings, "VISION_MODEL", "")
        monkeypatch.setattr(settings, "TAOTOKEN_VISION_MODEL", "")
    if case == "failure":
        provider.error = True
    if case == "ownership":
        other = User(email="private@example.com", username="private", hashed_password="x")
        db.add(other)
        db.flush()
        attachment.user_id = other.id
        db.commit()
    try:
        response = client.post(f"/api/conversations/{conversation.id}{suffix}", json={
            "content": "describe", "model_tier": "fast" if case == "unsupported" else "standard",
            "attachment_ids": [attachment.id]})
        if case == "success" and suffix.endswith("stream"):
            expected = 200
            assert "event: done" in response.text
        assert response.status_code == expected, response.text
        if case == "unsupported":
            assert "当前模型不支持图片理解，请切换支持图片的模型" in response.text
        if case != "success":
            db.refresh(attachment)
            assert attachment.message_id is None
            assert db.scalars(select(UsageRecord)).all() == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_image_read_error_maps_to_distinct_http_detail(client, db, monkeypatch, setup_vision):
    """发送阶段图片读取失败必须返回专用 400 文案，而不是笼统的 LLM 服务错误。"""
    user, conversation, attachment, provider = setup_vision
    app.dependency_overrides[get_current_user] = lambda: user

    class FailingProvider:
        def complete(self, messages, *, model=None):
            raise LLMImageError("image_read_failed", "图片读取失败，请重新上传")

    monkeypatch.setattr(chat, "get_vision_provider", lambda label: FailingProvider())
    try:
        response = client.post(f"/api/conversations/{conversation.id}/chat", json={
            "content": "describe", "model_tier": "standard", "attachment_ids": [attachment.id]})
        assert response.status_code == 400, response.text
        assert "图片读取失败，请重新上传" in response.text
        assert "LLM 服务错误" not in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_stream_charge_failure_emits_existing_error_event(client, db, setup_vision):
    user, conversation, attachment, provider = setup_vision
    provider.usage = LLMUsage(prompt_tokens=1000000, completion_tokens=1000000)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.post(f"/api/conversations/{conversation.id}/chat/stream", json={
            "content": "describe", "model_tier": "standard", "attachment_ids": [attachment.id]})
        assert response.status_code == 200
        assert "insufficient_credits" in response.text
        assert "event: done" not in response.text
        db.refresh(attachment)
        assert attachment.message_id is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_chat_response_and_reload_include_attachments(client, db, setup_vision):
    """Wave C: image history — both the chat response and a later conversation
    reload must carry the bound attachments (id + display url)."""
    user, conversation, attachment, provider = setup_vision
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.post(f"/api/conversations/{conversation.id}/chat", json={
            "content": "describe", "model_tier": "standard",
            "attachment_ids": [attachment.id]})
        assert response.status_code == 201, response.text
        chat_user = response.json()["user_message"]
        assert chat_user["attachments"] == [
            {"id": attachment.id, "url": f"/api/chat/attachments/{attachment.id}"}
        ] or chat_user["attachments"][0]["id"] == attachment.id
        assert chat_user["attachments"][0]["url"] == f"/api/chat/attachments/{attachment.id}"

        reloaded = client.get(f"/api/conversations/{conversation.id}/messages")
        assert reloaded.status_code == 200
        reload_user = [m for m in reloaded.json() if m["role"] == "user"][0]
        assert reload_user["attachments"], "reloaded user message lost its attachment"
        assert reload_user["attachments"][0]["id"] == attachment.id
        assert reload_user["attachments"][0]["url"].startswith("/api/chat/attachments/")
        assert reload_user["attachments"][0]["original_name"] == "test.png"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_image_only_message_reaches_vision_provider(db, setup_vision):
    """纯图片消息（content=""）必须到达 vision provider，且不带空文本 part。"""
    user, conversation, attachment, provider = setup_vision
    result = chat.send_chat_message(db, user.id, conversation.id, "",
                                    model_tier="standard", attachment_ids=[attachment.id])
    assert result.assistant_message.model == "vision-model"
    assert provider.calls, "vision provider was never called"
    messages, _model = provider.calls[0]
    user_msgs = [m for m in messages if m.role == "user"]
    assert user_msgs
    parts = user_msgs[-1].content_parts or []
    assert any(isinstance(p, ImagePart) for p in parts), "image part missing"
    assert not any(isinstance(p, TextPart) and not p.text for p in parts), \
        "empty text part must not be emitted for image-only messages"


def test_image_only_api_and_billing(client, db, setup_vision):
    """纯图片 API：201、附件绑定、usage 记录、积分扣减正常。"""
    user, conversation, attachment, provider = setup_vision
    provider.usage = LLMUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5)
    app.dependency_overrides[get_current_user] = lambda: user
    balance_before = get_balance(db, user.id)
    try:
        response = client.post(f"/api/conversations/{conversation.id}/chat", json={
            "content": "", "model_tier": "standard", "attachment_ids": [attachment.id]})
        assert response.status_code == 201, response.text
        chat_user = response.json()["user_message"]
        assert chat_user["content"] == ""
        assert chat_user["attachments"][0]["id"] == attachment.id
        db.refresh(attachment)
        assert attachment.message_id is not None
        assert db.scalars(select(UsageRecord)).all(), "no usage record for image-only message"
        assert get_balance(db, user.id) <= balance_before
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("suffix", ["/chat", "/chat/stream"])
def test_empty_message_rejected_without_attachments(client, db, setup_vision, suffix):
    """完全空消息（无文字且无附件）仍被 422 拒绝。"""
    user, conversation, attachment, provider = setup_vision
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.post(f"/api/conversations/{conversation.id}{suffix}",
                               json={"content": "   "})
        assert response.status_code == 422, response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
