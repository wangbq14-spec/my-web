import json

import pytest
from sqlalchemy import select

from app.api.routes import agent as agent_route
from app.llm.base import LLMError, LLMResponse, LLMToolCall, LLMUpstreamError
from app.models.message import Message


class FakeProvider:
    def __init__(self):
        self.responses = []
        self.calls = []

    def complete(self, messages, *, model=None, tools=None):
        self.calls.append({"messages": list(messages), "model": model, "tools": tools})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture()
def fake_provider(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(agent_route, "get_llm_provider", lambda: provider)
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
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    ).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_conversation(client, token):
    return client.post(
        "/api/conversations", json={"title": "agent"}, headers=_auth(token)
    ).json()["id"]


def _parse_sse(text):
    events = []
    for block in text.split("\n\n"):
        event_type = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type is not None:
            events.append({"event": event_type, "data": data})
    return events


def _call(name="calculator", arguments='{"expression":"2+2"}'):
    return LLMToolCall(id="call_1", name=name, arguments=arguments)


def test_agent_stream_unauthorized(client, fake_provider):
    response = client.post("/api/conversations/1/agent/stream", json={"content": "hi"})

    assert response.status_code == 401


def test_agent_stream_other_users_conversation_is_404(client, fake_provider):
    alice = _register_and_login(client, "alice")
    bob = _register_and_login(client, "bob")
    conversation_id = _create_conversation(client, bob)

    response = client.post(
        f"/api/conversations/{conversation_id}/agent/stream",
        json={"content": "hi"},
        headers=_auth(alice),
    )

    assert response.status_code == 404


def test_agent_stream_start_step_delta_and_done(client, fake_provider):
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)
    fake_provider.responses = [LLMResponse(content="final", model="fake-agent-model")]

    response = client.post(
        f"/api/conversations/{conversation_id}/agent/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    events = _parse_sse(response.text)
    assert response.status_code == 200
    assert events[0] == {
        "event": "start",
        "data": {"conversation_id": conversation_id, "agent": True},
    }
    assert [event["event"] for event in events] == [
        "start",
        "agent_step",
        "delta",
        "done",
    ]
    assert events[-1]["data"]["model"] == "fake-agent-model"


def test_agent_stream_tool_events_are_safe_and_ordered(client, fake_provider):
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)
    fake_provider.responses = [
        LLMResponse(tool_calls=[_call()]),
        LLMResponse(content="the answer"),
    ]

    response = client.post(
        f"/api/conversations/{conversation_id}/agent/stream",
        json={"content": "calculate"},
        headers=_auth(token),
    )

    events = _parse_sse(response.text)
    assert [event["event"] for event in events] == [
        "start",
        "agent_step",
        "tool_start",
        "tool_result",
        "agent_step",
        "delta",
        "done",
    ]
    tool_result = next(event["data"] for event in events if event["event"] == "tool_result")
    assert tool_result == {
        "tool_call_id": "call_1",
        "name": "calculator",
        "success": True,
        "summary": "完成",
    }
    assert not {"content", "data", "exception"} & tool_result.keys()


def test_agent_stream_llm_error_is_safe_and_rolls_back(client, db, fake_provider):
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)
    fake_provider.responses = [
        LLMUpstreamError("sk-secret https://private.example/v1 reasoning private")
    ]

    response = client.post(
        f"/api/conversations/{conversation_id}/agent/stream",
        json={"content": "hi"},
        headers=_auth(token),
    )

    events = _parse_sse(response.text)
    assert [event["event"] for event in events] == ["start", "agent_step", "error"]
    assert events[-1]["data"] == {"code": "upstream_error", "message": "LLM 上游服务错误"}
    assert db.execute(
        select(Message).where(Message.conversation_id == conversation_id)
    ).scalars().all() == []
    assert "sk-secret" not in response.text
    assert "private.example" not in response.text
    assert "reasoning" not in response.text
    assert "chain" not in response.text


def test_agent_stream_knowledge_tool_result_does_not_expose_full_data(
    client, fake_provider, monkeypatch
):
    from app.agent.tools import knowledge_search

    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)
    monkeypatch.setattr(knowledge_search, "retrieve", lambda *args: [])
    fake_provider.responses = [
        LLMResponse(
            tool_calls=[
                LLMToolCall(
                    id="search_1",
                    name="knowledge_search",
                    arguments='{"query":"sensitive corpus"}',
                )
            ]
        ),
        LLMResponse(content="final"),
    ]

    response = client.post(
        f"/api/conversations/{conversation_id}/agent/stream",
        json={"content": "search"},
        headers=_auth(token),
    )

    text = response.text
    tool_result = next(
        event["data"] for event in _parse_sse(text) if event["event"] == "tool_result"
    )
    assert tool_result["summary"] == "完成"
    assert "sensitive corpus" not in text
    assert "reasoning" not in text
    assert "chain" not in text
