import inspect
from datetime import datetime

import pytest
from sqlalchemy import select

from app.llm.base import LLMError, LLMResponse, LLMTimeoutError, LLMUpstreamError
from app.models.message import Message
from app.models.project import Project
from app.models.user import User
from app.schemas.conversation import ConversationCreate
from app.services import chat
from app.services.chat import ChatResult, send_chat_message
from app.services.conversation import create_conversation


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.response = LLMResponse(content="fake-reply", model="fake-model")
        self.error = None

    def complete(self, messages, *, model=None):
        self.calls.append({"messages": list(messages), "model": model})
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture()
def fake_provider(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(chat, "get_llm_provider", lambda: provider)
    return provider


def _create_user(db, username="alice"):
    user = User(email=f"{username}@example.com", username=username, hashed_password="x")
    db.add(user)
    db.flush()
    return user.id


def _create_conversation(db, user_id, model=None):
    return create_conversation(db, user_id, ConversationCreate(title="c1", model=model))


def test_send_chat_message_success(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)

    result = send_chat_message(db, user_id, conv.id, "你好")

    assert isinstance(result, ChatResult)
    assert result.user_message.role == "user"
    assert result.assistant_message.role == "assistant"
    assert result.assistant_message.content == "fake-reply"
    assert result.assistant_message.model == "fake-model"


def test_conversation_model_passed_to_provider(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id, model="gpt-4")

    send_chat_message(db, user_id, conv.id, "hi")

    assert fake_provider.calls[0]["model"] == "gpt-4"


def test_conversation_model_none_passes_none(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id, model=None)

    send_chat_message(db, user_id, conv.id, "hi")

    assert fake_provider.calls[0]["model"] is None


def test_history_sorted_asc(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)

    m1 = Message(conversation_id=conv.id, role="user", content="first")
    m2 = Message(conversation_id=conv.id, role="assistant", content="second")
    m1.created_at = datetime(2025, 1, 1, 8, 0, 0)
    m2.created_at = datetime(2025, 1, 2, 8, 0, 0)
    db.add_all([m1, m2])
    db.flush()

    send_chat_message(db, user_id, conv.id, "third")

    contents = [m.content for m in fake_provider.calls[0]["messages"]]
    assert contents == ["first", "second", "third"]


def test_multiturn_role_order(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)

    db.add(Message(conversation_id=conv.id, role="user", content="q1"))
    db.add(Message(conversation_id=conv.id, role="assistant", content="a1"))
    db.flush()

    send_chat_message(db, user_id, conv.id, "q2")

    roles = [m.role for m in fake_provider.calls[0]["messages"]]
    assert roles == ["user", "assistant", "user"]


def test_project_instructions_are_appended_as_a_system_message(db, fake_provider):
    user_id = _create_user(db, "alice")
    project = Project(user_id=user_id, name="project", instructions="be concise")
    db.add(project)
    db.flush()
    conversation = create_conversation(
        db, user_id, ConversationCreate(title="c1", project_id=project.id)
    )

    send_chat_message(db, user_id, conversation.id, "hello")

    messages = fake_provider.calls[0]["messages"]
    assert messages[0].role == "system"
    assert "[项目指令]\nbe concise" in messages[0].content
    assert messages[-1].content == "hello"


def test_cannot_chat_on_other_users_conversation(db, fake_provider):
    user_a = _create_user(db, "alice")
    user_b = _create_user(db, "bob")
    conv_b = _create_conversation(db, user_b)

    result = send_chat_message(db, user_a, conv_b.id, "hi")

    assert result is None
    assert fake_provider.calls == []


def test_nonexistent_conversation_returns_none_without_provider(db, fake_provider):
    user_a = _create_user(db, "alice")

    result = send_chat_message(db, user_a, 999999, "hi")

    assert result is None
    assert fake_provider.calls == []


def test_ownership_failure_creates_no_message(db, fake_provider):
    user_a = _create_user(db, "alice")
    user_b = _create_user(db, "bob")
    conv_b = _create_conversation(db, user_b)

    send_chat_message(db, user_a, conv_b.id, "hi")

    count = db.execute(
        select(Message).where(Message.conversation_id == conv_b.id)
    ).scalars().all()
    assert count == []


def test_provider_timeout_propagates(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    fake_provider.error = LLMTimeoutError("timeout")

    with pytest.raises(LLMTimeoutError):
        send_chat_message(db, user_id, conv.id, "hi")


def test_provider_upstream_error_propagates(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    fake_provider.error = LLMUpstreamError("boom")

    with pytest.raises(LLMUpstreamError):
        send_chat_message(db, user_id, conv.id, "hi")


def test_llm_failure_does_not_commit(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    fake_provider.error = LLMError("boom")

    with pytest.raises(LLMError):
        send_chat_message(db, user_id, conv.id, "hi")

    db.rollback()

    count = db.execute(
        select(Message).where(Message.conversation_id == conv.id)
    ).scalars().all()
    assert count == []


def test_service_has_no_commit_call():
    source = inspect.getsource(send_chat_message)
    assert ".commit(" not in source
    assert "commit()" not in source


def test_conversation_updated_at_updated(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    conv.updated_at = datetime(2020, 1, 1, 0, 0, 0)
    db.flush()

    send_chat_message(db, user_id, conv.id, "hi")

    assert conv.updated_at != datetime(2020, 1, 1, 0, 0, 0)
