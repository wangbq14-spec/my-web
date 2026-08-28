import inspect
import json

import pytest
from sqlalchemy import select

from app.api.routes import conversations
from app.llm.base import LLMChunk, LLMConfigurationError, LLMTimeoutError, LLMUpstreamError
from app.models.message import Message
from app.services import chat
from app.services.chat import stream_chat_message


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


def _register_and_login(client, username):
    client.post(
        "/api/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "secret123",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    )
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_conversation(client, token):
    resp = client.post("/api/conversations", json={"title": "c1"}, headers=_auth(token))
    return resp.json()["id"]


def _parse_sse(text):
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = None
        data = None
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event_type is not None:
            events.append({"event": event_type, "data": data})
    return events


def test_stream_unauthorized(client, fake_provider):
    resp = client.post("/api/conversations/1/chat/stream", json={"content": "hi"})

    assert resp.status_code == 401


def test_stream_success_events(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.chunks = ["你", "好"]

    resp = client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    types = [e["event"] for e in events]

    assert types[0] == "start"
    assert types[-1] == "done"
    assert types.count("delta") == 2
    assert [e["data"]["content"] for e in events if e["event"] == "delta"] == ["你", "好"]
    done = events[-1]["data"]
    assert "user_message_id" in done
    assert "assistant_message_id" in done
    assert done["model"] == "fake-stream-model"


def test_stream_delta_join_matches_assistant_content(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.chunks = ["你", "好", "呀"]

    client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    msgs = db.execute(
        select(Message).where(Message.conversation_id == conv_id)
    ).scalars().all()
    assistant = next(m for m in msgs if m.role == "assistant")
    assert assistant.content == "你好呀"


def test_stream_success_persists_two_messages(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.chunks = ["ok"]

    client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    msgs = db.execute(
        select(Message).where(Message.conversation_id == conv_id)
    ).scalars().all()
    assert len(msgs) == 2
    assert {m.role for m in msgs} == {"user", "assistant"}


def test_stream_assistant_role_backend_fixed(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.chunks = ["ok"]

    client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assistant = db.execute(
        select(Message).where(
            Message.conversation_id == conv_id, Message.role == "assistant"
        )
    ).scalar_one()
    assert assistant.role == "assistant"


def test_stream_assistant_model(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.chunks = ["ok"]
    fake_provider.model = "fake-stream-model"

    client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assistant = db.execute(
        select(Message).where(
            Message.conversation_id == conv_id, Message.role == "assistant"
        )
    ).scalar_one()
    assert assistant.model == "fake-stream-model"


def test_stream_updated_at(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.chunks = ["ok"]

    before = client.get(
        f"/api/conversations/{conv_id}", headers=_auth(token)
    ).json()["updated_at"]

    client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    after = client.get(
        f"/api/conversations/{conv_id}", headers=_auth(token)
    ).json()["updated_at"]

    assert after != before


def test_stream_other_users_404(client, fake_provider):
    token_a = _register_and_login(client, "alice")
    token_b = _register_and_login(client, "bob")
    conv_b = _create_conversation(client, token_b)

    resp = client.post(
        f"/api/conversations/{conv_b}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token_a),
    )

    assert resp.status_code == 404


def test_stream_nonexistent_404(client, fake_provider):
    token = _register_and_login(client, "alice")

    resp = client.post(
        "/api/conversations/999999/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 404


def test_stream_role_extra_422(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi", "role": "assistant"},
        headers=_auth(token),
    )

    assert resp.status_code == 422


def test_stream_conversation_id_extra_422(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi", "conversation_id": conv_id},
        headers=_auth(token),
    )

    assert resp.status_code == 422


def test_stream_empty_content_422(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": ""},
        headers=_auth(token),
    )

    assert resp.status_code == 422


def test_stream_config_error_503(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.before_error = LLMConfigurationError("missing")

    resp = client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 503


def test_stream_timeout_504(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.before_error = LLMTimeoutError("timeout")

    resp = client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 504


def test_stream_upstream_error_502(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.before_error = LLMUpstreamError("boom")

    resp = client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 502


def test_stream_mid_error_sends_error_event(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.chunks = ["你", "好"]
    fake_provider.after_error = LLMUpstreamError("boom")

    resp = client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["event"] for e in events]
    assert types[0] == "start"
    assert "delta" in types
    assert types[-1] == "error"
    assert events[-1]["data"]["code"] == "upstream_error"


def test_stream_mid_error_no_residual_message(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.chunks = ["你", "好"]
    fake_provider.after_error = LLMUpstreamError("boom")

    client.post(
        f"/api/conversations/{conv_id}/chat/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    msgs = db.execute(
        select(Message).where(Message.conversation_id == conv_id)
    ).scalars().all()
    assert msgs == []


def test_stream_commits_once():
    source = inspect.getsource(conversations.chat_stream)
    assert source.count("db.commit()") == 1


def test_stream_service_no_commit():
    source = inspect.getsource(stream_chat_message)
    assert ".commit(" not in source
