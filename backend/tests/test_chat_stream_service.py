import inspect
from datetime import datetime

import pytest

from app.llm.base import LLMChunk, LLMError, LLMUpstreamError
from app.models.message import Message
from app.models.user import User
from app.schemas.conversation import ConversationCreate
from app.services import chat
from app.services.chat import stream_chat_message
from app.services.conversation import create_conversation


class FakeStreamingProvider:
    def __init__(self):
        self.calls = []
        self.chunks = []
        self.before_error = None
        self.after_error = None
        self.model = "fake-stream-model"

    def stream(self, messages, *, model=None):
        self.calls.append({"messages": list(messages), "model": model})
        if self.before_error is not None:
            raise self.before_error
        for i, content in enumerate(self.chunks):
            if self.after_error is not None and i == 1:
                raise self.after_error
            yield LLMChunk(content=content, model=self.model if i == 0 else None)


@pytest.fixture()
def fake_provider(monkeypatch):
    provider = FakeStreamingProvider()
    monkeypatch.setattr(chat, "get_llm_provider", lambda: provider)
    return provider


def _create_user(db, username="alice"):
    user = User(email=f"{username}@example.com", username=username, hashed_password="x")
    db.add(user)
    db.flush()
    return user.id


def _create_conversation(db, user_id, model=None):
    return create_conversation(db, user_id, ConversationCreate(title="c1", model=model))


def test_stream_delta_and_done(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    fake_provider.chunks = ["你", "好"]

    events = list(stream_chat_message(db, user_id, conv.id, "hi"))

    deltas = [e for e in events if e.type == "delta"]
    done = [e for e in events if e.type == "done"]

    assert [e.content for e in deltas] == ["你", "好"]
    assert len(done) == 1
    assert done[0].user_message_id is not None
    assert done[0].assistant_message_id is not None


def test_stream_assistant_content_joined(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    fake_provider.chunks = ["你", "好", "呀"]

    events = list(stream_chat_message(db, user_id, conv.id, "hi"))
    done = next(e for e in events if e.type == "done")

    assistant = db.get(Message, done.assistant_message_id)
    assert assistant.content == "你好呀"


def test_stream_roles_backend_fixed(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    fake_provider.chunks = ["ok"]

    events = list(stream_chat_message(db, user_id, conv.id, "hi"))
    done = next(e for e in events if e.type == "done")

    user = db.get(Message, done.user_message_id)
    assistant = db.get(Message, done.assistant_message_id)
    assert user.role == "user"
    assert assistant.role == "assistant"


def test_stream_model_from_chunk(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    fake_provider.chunks = ["ok"]
    fake_provider.model = "actual-model"

    events = list(stream_chat_message(db, user_id, conv.id, "hi"))
    done = next(e for e in events if e.type == "done")

    assistant = db.get(Message, done.assistant_message_id)
    assert assistant.model == "actual-model"


def test_stream_conversation_model_override(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id, model="gpt-4")
    fake_provider.chunks = ["ok"]

    list(stream_chat_message(db, user_id, conv.id, "hi"))

    assert fake_provider.calls[0]["model"] == "gpt-4"


def test_stream_model_none_passes_none(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id, model=None)
    fake_provider.chunks = ["ok"]

    list(stream_chat_message(db, user_id, conv.id, "hi"))

    assert fake_provider.calls[0]["model"] is None


def test_stream_ownership_not_found(db, fake_provider):
    user_a = _create_user(db, "alice")
    user_b = _create_user(db, "bob")
    conv_b = _create_conversation(db, user_b)
    fake_provider.chunks = ["ok"]

    events = list(stream_chat_message(db, user_a, conv_b.id, "hi"))

    assert [e.type for e in events] == ["not_found"]
    assert fake_provider.calls == []


def test_stream_history_order(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)

    m1 = Message(conversation_id=conv.id, role="user", content="first")
    m2 = Message(conversation_id=conv.id, role="assistant", content="second")
    m1.created_at = datetime(2025, 1, 1, 8, 0, 0)
    m2.created_at = datetime(2025, 1, 2, 8, 0, 0)
    db.add_all([m1, m2])
    db.flush()

    fake_provider.chunks = ["ok"]
    list(stream_chat_message(db, user_id, conv.id, "third"))

    contents = [m.content for m in fake_provider.calls[0]["messages"]]
    assert contents == ["first", "second", "third"]


def test_stream_mid_error_propagates(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    fake_provider.chunks = ["你", "好"]
    fake_provider.after_error = LLMUpstreamError("boom")

    with pytest.raises(LLMUpstreamError):
        list(stream_chat_message(db, user_id, conv.id, "hi"))


def test_stream_empty_content_raises(db, fake_provider):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    fake_provider.chunks = []

    with pytest.raises(LLMError):
        list(stream_chat_message(db, user_id, conv.id, "hi"))


def test_stream_service_no_commit():
    source = inspect.getsource(stream_chat_message)
    assert ".commit(" not in source
