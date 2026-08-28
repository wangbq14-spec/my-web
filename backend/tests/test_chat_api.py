import inspect

import pytest
from sqlalchemy import select

from app.api.routes import conversations
from app.llm.base import (
    LLMConfigurationError,
    LLMResponse,
    LLMTimeoutError,
    LLMUpstreamError,
)
from app.models.message import Message
from app.services import chat


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


def _create_conversation(client, token, title="c1"):
    resp = client.post("/api/conversations", json={"title": title}, headers=_auth(token))
    return resp.json()["id"]


def test_chat_unauthorized(client, fake_provider):
    resp = client.post("/api/conversations/1/chat", json={"content": "hi"})

    assert resp.status_code == 401


def test_chat_success_response_structure(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "你好"},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    data = resp.json()
    assert "user_message" in data
    assert "assistant_message" in data
    assert data["user_message"]["role"] == "user"
    assert data["assistant_message"]["role"] == "assistant"
    assert data["assistant_message"]["content"] == "fake-reply"
    assert data["assistant_message"]["model"] == "fake-model"


def test_chat_own_conversation_persists_both_messages(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    msgs = db.execute(
        select(Message).where(Message.conversation_id == conv_id)
    ).scalars().all()
    assert len(msgs) == 2
    assert {m.role for m in msgs} == {"user", "assistant"}


def test_chat_other_users_conversation_404(client, fake_provider):
    token_a = _register_and_login(client, "alice")
    token_b = _register_and_login(client, "bob")
    conv_b = _create_conversation(client, token_b)

    resp = client.post(
        f"/api/conversations/{conv_b}/chat",
        json={"content": "hi"},
        headers=_auth(token_a),
    )

    assert resp.status_code == 404


def test_chat_nonexistent_conversation_404(client, fake_provider):
    token = _register_and_login(client, "alice")

    resp = client.post(
        "/api/conversations/999999/chat",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 404


def test_chat_body_role_422(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "hi", "role": "assistant"},
        headers=_auth(token),
    )

    assert resp.status_code == 422


def test_chat_body_conversation_id_422(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "hi", "conversation_id": conv_id},
        headers=_auth(token),
    )

    assert resp.status_code == 422


def test_chat_empty_content_422(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": ""},
        headers=_auth(token),
    )

    assert resp.status_code == 422


def test_chat_timeout_504(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.error = LLMTimeoutError("timeout")

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 504


def test_chat_upstream_error_502(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.error = LLMUpstreamError("boom")

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 502


def test_chat_configuration_error_503(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.error = LLMConfigurationError("missing config")

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 503


def test_chat_timeout_no_residual_message(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.error = LLMTimeoutError("timeout")

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 504
    msgs = db.execute(
        select(Message).where(Message.conversation_id == conv_id)
    ).scalars().all()
    assert msgs == []


def test_chat_upstream_error_no_residual_message(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    fake_provider.error = LLMUpstreamError("boom")

    resp = client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "hi"},
        headers=_auth(token),
    )

    assert resp.status_code == 502
    msgs = db.execute(
        select(Message).where(Message.conversation_id == conv_id)
    ).scalars().all()
    assert msgs == []


def test_chat_updates_updated_at(client, fake_provider):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    before = client.get(
        f"/api/conversations/{conv_id}", headers=_auth(token)
    ).json()["updated_at"]

    client.post(
        f"/api/conversations/{conv_id}/chat",
        json={"content": "hi"},
        headers=_auth(token),
    )

    after = client.get(
        f"/api/conversations/{conv_id}", headers=_auth(token)
    ).json()["updated_at"]

    assert after != before


def test_chat_router_does_not_touch_orm():
    source = inspect.getsource(conversations.chat)

    assert "Message(" not in source
    assert "session.add" not in source
    assert "select(" not in source
    assert "chat_service.send_chat_message" in source
