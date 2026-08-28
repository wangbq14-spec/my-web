import inspect
import json

import pytest
from sqlalchemy import select

from app.api.routes import conversations
from app.llm.base import LLMChunk, LLMUpstreamError
from app.models.message import Message
from app.services import chat
from app.services.chat import regenerate_chat_message


class FakeStreamingProvider:
    def __init__(self):
        self.calls = []
        self.chunks = []
        self.before_error = None
        self.after_error = None
        self.model = "fake-regenerate-model"

    def stream(self, messages, *, model=None):
        self.calls.append({"messages": list(messages), "model": model})
        if self.before_error is not None:
            raise self.before_error
        for index, content in enumerate(self.chunks):
            if self.after_error is not None and index == 1:
                raise self.after_error
            yield LLMChunk(content=content, model=self.model if index == 0 else None)


@pytest.fixture()
def fake_provider(monkeypatch):
    provider = FakeStreamingProvider()
    monkeypatch.setattr(chat, "get_llm_provider", lambda: provider)
    return provider


def _register_and_login(client, username):
    client.post(
        "/api/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "secret123",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    )
    return response.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_conversation(client, token):
    response = client.post("/api/conversations", json={"title": "c1"}, headers=_auth(token))
    return response.json()["id"]


def _parse_sse(text):
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event_type is not None:
            events.append({"event": event_type, "data": data})
    return events


def _seed_chat(client, token, conversation_id, fake_provider):
    fake_provider.chunks = ["first"]
    response = client.post(
        f"/api/conversations/{conversation_id}/chat/stream",
        json={"content": "question"},
        headers=_auth(token),
    )
    assert response.status_code == 200


def _messages(db, conversation_id):
    return db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).scalars().all()


def test_regenerate_does_not_duplicate_user_message(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)
    _seed_chat(client, token, conversation_id, fake_provider)
    fake_provider.chunks = ["regenerated"]

    response = client.post(
        f"/api/conversations/{conversation_id}/regenerate/stream", headers=_auth(token)
    )

    assert response.status_code == 200
    messages = _messages(db, conversation_id)
    assert [message.role for message in messages].count("user") == 1
    assert [message.role for message in messages].count("assistant") == 2


def test_regenerate_adds_assistant_with_joined_content(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)
    _seed_chat(client, token, conversation_id, fake_provider)
    fake_provider.chunks = ["new ", "answer"]

    client.post(
        f"/api/conversations/{conversation_id}/regenerate/stream", headers=_auth(token)
    )

    assert _messages(db, conversation_id)[-1].content == "new answer"


def test_regenerate_other_users_conversation_is_404(client, fake_provider):
    token_a = _register_and_login(client, "alice")
    token_b = _register_and_login(client, "bob")
    conversation_id = _create_conversation(client, token_b)

    response = client.post(
        f"/api/conversations/{conversation_id}/regenerate/stream", headers=_auth(token_a)
    )

    assert response.status_code == 404


def test_regenerate_mid_stream_error_rolls_back(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)
    _seed_chat(client, token, conversation_id, fake_provider)
    fake_provider.chunks = ["partial", "answer"]
    fake_provider.after_error = LLMUpstreamError("boom")

    response = client.post(
        f"/api/conversations/{conversation_id}/regenerate/stream", headers=_auth(token)
    )

    assert _parse_sse(response.text)[-1]["event"] == "error"
    assert len(_messages(db, conversation_id)) == 2


def test_regenerate_streams_start_deltas_and_done(client, fake_provider):
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)
    _seed_chat(client, token, conversation_id, fake_provider)
    fake_provider.chunks = ["new ", "answer"]

    response = client.post(
        f"/api/conversations/{conversation_id}/regenerate/stream", headers=_auth(token)
    )

    events = _parse_sse(response.text)
    assert [event["event"] for event in events] == ["start", "delta", "delta", "done"]
    done = events[-1]["data"]
    assert done["assistant_message_id"]
    assert done["model"] == "fake-regenerate-model"


def test_regenerate_without_user_message_sends_error_event(client, fake_provider):
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    response = client.post(
        f"/api/conversations/{conversation_id}/regenerate/stream", headers=_auth(token)
    )

    events = _parse_sse(response.text)
    assert [event["event"] for event in events] == ["start", "error"]
    assert events[-1]["data"]["code"] == "no_user_message"


def test_regenerate_stream_commits_once_and_rolls_back_if_uncommitted():
    source = inspect.getsource(conversations.regenerate_stream)
    assert source.count("db.commit()") == 1
    assert "finally:" in source
    assert "db.rollback()" in source


def test_regenerate_service_does_not_commit():
    assert ".commit(" not in inspect.getsource(regenerate_chat_message)
