import json

import pytest
from pydantic import ValidationError

from app.agent.base import ToolContext
from app.agent.tools import knowledge_search
from app.agent.tools.knowledge_search import KnowledgeSearchInput, KnowledgeSearchTool
from app.rag.embeddings.base import EmbeddingError
from app.rag.retrieval import RetrievedChunk


def test_knowledge_search_serializes_chunks_and_uses_context_user(monkeypatch):
    received: dict[str, object] = {}
    chunks = [
        RetrievedChunk(7, "guide.txt", 2, "relevant knowledge", 0.95),
    ]

    def fake_retrieve(session, user_id, query, top_k):
        received.update(session=session, user_id=user_id, query=query, top_k=top_k)
        return chunks

    monkeypatch.setattr(knowledge_search, "retrieve", fake_retrieve)
    context = ToolContext(user_id=42, session=object())

    result = KnowledgeSearchTool().execute(
        KnowledgeSearchInput(query="find guide", top_k=3), context
    )

    assert result.success is True
    assert received == {
        "session": context.session,
        "user_id": 42,
        "query": "find guide",
        "top_k": 3,
    }
    assert result.data == {
        "chunks": [
            {
                "document_id": 7,
                "filename": "guide.txt",
                "chunk_index": 2,
                "content": "relevant knowledge",
                "score": 0.95,
            }
        ]
    }
    assert json.loads(result.content) == result.data["chunks"]


def test_knowledge_search_returns_safe_error_for_embedding_failure(monkeypatch):
    def fake_retrieve(*args):
        raise EmbeddingError("provider details must remain private")

    monkeypatch.setattr(knowledge_search, "retrieve", fake_retrieve)

    result = KnowledgeSearchTool().execute(
        KnowledgeSearchInput(query="find"), ToolContext(user_id=1, session=object())
    )

    assert result.success is False
    assert result.error_code == "retrieval_error"
    assert result.content == "知识库检索失败"


def test_knowledge_search_bounds_returned_chunk_content(monkeypatch):
    monkeypatch.setattr(
        knowledge_search,
        "retrieve",
        lambda *args: [
            RetrievedChunk(1, "one.txt", 0, "abcd", 0.9),
            RetrievedChunk(2, "two.txt", 0, "efgh", 0.8),
        ],
    )
    monkeypatch.setattr(knowledge_search.settings, "RAG_MAX_CONTEXT_CHARS", 6)

    result = KnowledgeSearchTool().execute(
        KnowledgeSearchInput(query="find"), ToolContext(user_id=1, session=object())
    )

    assert result.data == {
        "chunks": [
            {
                "document_id": 1,
                "filename": "one.txt",
                "chunk_index": 0,
                "content": "abcd",
                "score": 0.9,
            },
            {
                "document_id": 2,
                "filename": "two.txt",
                "chunk_index": 0,
                "content": "ef",
                "score": 0.8,
            },
        ]
    }


def test_knowledge_search_input_does_not_accept_user_id():
    properties = KnowledgeSearchInput.model_json_schema()["properties"]
    assert "user_id" not in properties

    with pytest.raises(ValidationError):
        KnowledgeSearchInput(query="find", user_id=999)
