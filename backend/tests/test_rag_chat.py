import inspect
import json

import pytest
from sqlalchemy import select

from app.api.routes import conversations
from app.llm.base import LLMChunk, LLMResponse, LLMUpstreamError
from app.models.message import Message
from app.rag.embeddings.base import EmbeddingError
from app.rag.retrieval import RetrievedChunk
from app.services import chat


class FakeRagChatProvider:
    def __init__(self):
        self.complete_calls = []
        self.stream_calls = []
        self.complete_error = None
        self.stream_error = None

    def complete(self, messages, *, model=None):
        self.complete_calls.append({"messages": list(messages), "model": model})
        if self.complete_error is not None:
            raise self.complete_error
        return LLMResponse(content="fake reply", model="fake-model")

    def stream(self, messages, *, model=None):
        self.stream_calls.append({"messages": list(messages), "model": model})
        if self.stream_error is not None:
            raise self.stream_error
        yield LLMChunk(content="fake ", model="fake-stream-model")
        yield LLMChunk(content="reply")


@pytest.fixture()
def fake_provider(monkeypatch):
    provider = FakeRagChatProvider()
    monkeypatch.setattr(chat, "get_llm_provider", lambda: provider)
    return provider


def _register_and_login(client, username: str) -> str:
    client.post(
        "/api/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "secret123",
        },
    )
    return client.post(
        "/api/auth/login", json={"username": username, "password": "secret123"}
    ).json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_conversation(client, token: str) -> int:
    return client.post("/api/conversations", json={"title": "c1"}, headers=_auth(token)).json()["id"]


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        event_type = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_type = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event_type:
            events.append({"event": event_type, "data": data})
    return events


def _retrieved() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            document_id=42,
            filename="handbook.txt",
            chunk_index=2,
            content="knowledge base evidence",
            score=0.98,
        )
    ]


def test_non_rag_chat_does_not_call_retrieve(client, fake_provider, monkeypatch):
    calls = []
    monkeypatch.setattr(chat, "retrieve", lambda *args: calls.append(args) or _retrieved())
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    response = client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"content": "hello"},
        headers=_auth(token),
    )

    assert response.status_code == 201
    assert calls == []
    assert response.json()["sources"] == []
    assert fake_provider.complete_calls[0]["messages"][0].role == "user"


def test_rag_chat_calls_retrieve_for_current_user_with_top_k(client, fake_provider, monkeypatch):
    observed = {}

    def fake_retrieve(session, user_id, query, top_k):
        observed.update(user_id=user_id, query=query, top_k=top_k)
        return _retrieved()

    monkeypatch.setattr(chat, "retrieve", fake_retrieve)
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    response = client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"content": "hello", "use_rag": True, "top_k": 3},
        headers=_auth(token),
    )

    assert response.status_code == 201
    assert observed == {"user_id": 1, "query": "hello", "top_k": 3}
    assert fake_provider.complete_calls[0]["messages"][0].role == "system"


def test_project_rag_prompt_orders_global_safety_rag_and_project_instructions(
    client, fake_provider, monkeypatch
):
    monkeypatch.setattr(chat, "retrieve", lambda *_args, **_kwargs: _retrieved())
    token = _register_and_login(client, "alice")
    project = client.post(
        "/api/projects",
        json={"name": "project", "instructions": "PROJECT-INSTRUCTION-MARKER"},
        headers=_auth(token),
    ).json()
    conversation_id = client.post(
        "/api/conversations",
        json={"title": "c1", "project_id": project["id"]},
        headers=_auth(token),
    ).json()["id"]

    response = client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"content": "hello", "use_rag": True},
        headers=_auth(token),
    )

    assert response.status_code == 201
    prompt = fake_provider.complete_calls[0]["messages"][0].content
    assert prompt.index("Follow all system-level safety") < prompt.index("<retrieved_documents>")
    assert prompt.index("<retrieved_documents>") < prompt.index("PROJECT-INSTRUCTION-MARKER")


def test_rag_chat_top_k_defaults_and_validates_bounds(client, fake_provider, monkeypatch):
    observed = []
    monkeypatch.setattr(
        chat,
        "retrieve",
        lambda _session, _user_id, _query, top_k: observed.append(top_k) or _retrieved(),
    )
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    default_response = client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"content": "hello", "use_rag": True},
        headers=_auth(token),
    )
    zero_response = client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"content": "hello", "use_rag": True, "top_k": 0},
        headers=_auth(token),
    )
    high_response = client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"content": "hello", "use_rag": True, "top_k": 21},
        headers=_auth(token),
    )

    assert default_response.status_code == 201
    assert observed == [5]
    assert zero_response.status_code == 422
    assert high_response.status_code == 422


def test_rag_non_stream_response_contains_citations(client, fake_provider, monkeypatch):
    monkeypatch.setattr(chat, "retrieve", lambda *_args: _retrieved())
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    response = client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"content": "hello", "use_rag": True},
        headers=_auth(token),
    )

    assert response.status_code == 201
    assert response.json()["sources"] == [
        {
            "document_id": 42,
            "filename": "handbook.txt",
            "chunk_index": 2,
            "score": 0.98,
            "excerpt": "knowledge base evidence",
        }
    ]


def test_rag_stream_sends_sources_before_deltas_and_done(client, fake_provider, monkeypatch):
    monkeypatch.setattr(chat, "retrieve", lambda *_args: _retrieved())
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    response = client.post(
        f"/api/conversations/{conversation_id}/chat/stream",
        json={"content": "hello", "use_rag": True},
        headers=_auth(token),
    )

    events = _parse_sse(response.text)
    event_types = [event["event"] for event in events]
    assert response.status_code == 200
    assert event_types == ["start", "sources", "delta", "delta", "done"]
    assert events[1]["data"]["sources"][0]["document_id"] == 42
    assert event_types.index("sources") < event_types.index("delta")
    assert events[-1]["data"]["user_message_id"]
    assert events[-1]["data"]["assistant_message_id"]


def test_rag_stream_with_empty_retrieval_sends_empty_sources_and_continues(
    client, fake_provider, monkeypatch
):
    monkeypatch.setattr(chat, "retrieve", lambda *_args: [])
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    response = client.post(
        f"/api/conversations/{conversation_id}/chat/stream",
        json={"content": "hello", "use_rag": True},
        headers=_auth(token),
    )

    events = _parse_sse(response.text)
    assert [event["event"] for event in events] == [
        "start",
        "sources",
        "delta",
        "delta",
        "done",
    ]
    assert events[1]["data"] == {"sources": []}
    assert "未检索到相关文档" in fake_provider.stream_calls[0]["messages"][0].content


def test_rag_retrieval_error_is_safe_and_leaves_no_messages(client, db, fake_provider, monkeypatch):
    monkeypatch.setattr(
        chat,
        "retrieve",
        lambda *_args: (_ for _ in ()).throw(
            EmbeddingError("api-key=secret base_url=https://private.example")
        ),
    )
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    response = client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"content": "hello", "use_rag": True},
        headers=_auth(token),
    )
    streamed = client.post(
        f"/api/conversations/{conversation_id}/chat/stream",
        json={"content": "hello", "use_rag": True},
        headers=_auth(token),
    )

    assert response.status_code == 502
    assert "知识库检索失败" in response.json()["detail"]
    assert "api-key" not in response.text
    assert "private.example" not in response.text
    events = _parse_sse(streamed.text)
    assert events == [
        {"event": "start", "data": {"conversation_id": conversation_id}},
        {
            "event": "error",
            "data": {"code": "retrieval_error", "message": "知识库检索失败，请稍后重试"},
        },
    ]
    assert db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all() == []


def test_rag_stream_llm_error_rolls_back(client, db, fake_provider, monkeypatch):
    monkeypatch.setattr(chat, "retrieve", lambda *_args: _retrieved())
    fake_provider.stream_error = LLMUpstreamError("upstream failed")
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    response = client.post(
        f"/api/conversations/{conversation_id}/chat/stream",
        json={"content": "hello", "use_rag": True},
        headers=_auth(token),
    )

    events = _parse_sse(response.text)
    assert events[-1]["data"]["code"] == "upstream_error"
    assert db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all() == []


def test_rag_stream_commits_only_on_done_and_regenerate_supports_rag():
    stream_source = inspect.getsource(conversations.chat_stream)
    regenerate_source = inspect.getsource(chat.regenerate_chat_message)

    assert stream_source.count("db.commit()") == 1
    assert "finally:" in stream_source
    assert "db.rollback()" in stream_source
    assert "_retrieve_for_conversation(" in regenerate_source


def test_regular_stream_has_no_sources_event(client, fake_provider, monkeypatch):
    calls = []
    monkeypatch.setattr(chat, "retrieve", lambda *args: calls.append(args) or _retrieved())
    token = _register_and_login(client, "alice")
    conversation_id = _create_conversation(client, token)

    response = client.post(
        f"/api/conversations/{conversation_id}/chat/stream",
        json={"content": "hello"},
        headers=_auth(token),
    )

    events = _parse_sse(response.text)
    assert calls == []
    assert [event["event"] for event in events] == ["start", "delta", "delta", "done"]
