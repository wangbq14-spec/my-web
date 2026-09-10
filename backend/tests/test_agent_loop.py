import inspect
import json
from datetime import datetime

import pytest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.agent.base import Tool, ToolContext, ToolResult
from app.agent.loop import run_agent
from app.agent.registry import ToolRegistry
from app.agent.tools.knowledge_search import KnowledgeSearchTool
from app.api.routes import agent as agent_route
from app.llm.base import LLMError, LLMResponse, LLMToolCall
from app.models.document import Document
from app.models.message import Message
from app.models.project import Project
from app.models.user import User
from app.rag import retrieval
from app.rag.vector_store.base import ChunkVector
from app.rag.vector_store.local import LocalVectorStore
from app.schemas.conversation import ConversationCreate
from app.services.conversation import create_conversation


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, *, model=None, tools=None):
        self.calls.append({"messages": list(messages), "model": model, "tools": tools})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeEmbeddingProvider:
    def embed_query(self, text: str) -> list[float]:
        del text
        return [1.0, 0.0]


class FakeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int = Field(ge=0)


class FakeTool(Tool):
    name = "fake_tool"
    description = "A test-only tool."
    input_schema = FakeInput

    def __init__(self, result=None, error=None):
        self.result = result or ToolResult(success=True, content="tool output")
        self.error = error
        self.calls = []

    def execute(self, args: FakeInput, context: ToolContext) -> ToolResult:
        self.calls.append((args, context.user_id))
        if self.error is not None:
            raise self.error
        return self.result


def _create_user(db, username="alice"):
    user = User(email=f"{username}@example.com", username=username, hashed_password="x")
    db.add(user)
    db.flush()
    return user.id


def _create_conversation(db, user_id):
    return create_conversation(db, user_id, ConversationCreate(title="agent"))


def _configure_real_rag(db, monkeypatch) -> LocalVectorStore:
    class NonClosingSession:
        def scalars(self, statement):
            return db.scalars(statement)

        def close(self) -> None:
            pass

    store = LocalVectorStore(NonClosingSession)
    monkeypatch.setattr(retrieval, "get_embedding_provider", FakeEmbeddingProvider)
    monkeypatch.setattr(retrieval, "get_vector_store", lambda: store)
    return store


def _index_agent_document(
    db,
    store: LocalVectorStore,
    *,
    user_id: int,
    filename: str,
    content: str,
    project_id: int | None,
) -> Document:
    document = Document(
        user_id=user_id,
        project_id=project_id,
        filename=f"stored-{filename}",
        original_filename=filename,
        content_type="text/plain",
        file_size=len(content),
        status="ready",
        processing_generation=1,
        active_generation=1,
    )
    db.add(document)
    db.flush()
    store.upsert_chunks(
        user_id,
        document.id,
        1,
        [ChunkVector(chunk_index=0, content=content, embedding=[1.0, 0.0])],
    )
    return document


def _registry(tool=None):
    registry = ToolRegistry()
    if tool is not None:
        registry.register(tool)
    return registry


def _call(call_id="call_1", name="fake_tool", arguments='{"value": 1}'):
    return LLMToolCall(id=call_id, name=name, arguments=arguments)


def test_agent_no_tool_direct_final(db):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    provider = FakeProvider([LLMResponse(content="final", model="fake-model")])

    events = list(
        run_agent(db, user_id, conversation.id, "hello", _registry(), provider, None, 2)
    )

    assert [event.type for event in events] == ["agent_step", "delta", "done"]
    assert events[-1].model == "fake-model"


def test_agent_project_instructions_are_injected_before_user_message(db):
    user_id = _create_user(db)
    project = Project(user_id=user_id, name="project", instructions="use bullets")
    db.add(project)
    db.flush()
    conversation = create_conversation(
        db, user_id, ConversationCreate(title="agent", project_id=project.id)
    )
    provider = FakeProvider([LLMResponse(content="final")])

    list(run_agent(db, user_id, conversation.id, "hello", _registry(), provider, None, 2))

    messages = provider.calls[0]["messages"]
    assert messages[0].role == "system"
    assert "[项目指令]\nuse bullets" in messages[0].content
    assert messages[-1].content == "hello"


def test_agent_completion_touches_project_activity(db):
    user_id = _create_user(db)
    project = Project(user_id=user_id, name="project")
    db.add(project)
    db.flush()
    conversation = create_conversation(
        db, user_id, ConversationCreate(title="agent", project_id=project.id)
    )
    project.last_activity_at = datetime(2020, 1, 1, 0, 0, 0)
    db.flush()

    list(
        run_agent(
            db,
            user_id,
            conversation.id,
            "hello",
            _registry(),
            FakeProvider([LLMResponse(content="final")]),
            None,
            2,
        )
    )

    db.refresh(project)
    assert project.last_activity_at > datetime(2020, 1, 1, 0, 0, 0)


def test_agent_single_tool_then_final(db):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    tool = FakeTool()
    provider = FakeProvider(
        [
            LLMResponse(tool_calls=[_call()]),
            LLMResponse(content="final", model="fake-model"),
        ]
    )

    events = list(
        run_agent(db, user_id, conversation.id, "hello", _registry(tool), provider, None, 3)
    )

    assert [event.type for event in events] == [
        "agent_step",
        "tool_start",
        "tool_result",
        "agent_step",
        "delta",
        "done",
    ]
    assert tool.calls[0][0].value == 1
    assert provider.calls[1]["messages"][-1].content == "tool output"


def test_project_agent_knowledge_search_uses_server_derived_project_scope(
    db, monkeypatch
):
    store = _configure_real_rag(db, monkeypatch)
    alice_id = _create_user(db, "alice")
    bob_id = _create_user(db, "bob")
    project_a = Project(user_id=alice_id, name="project-a")
    project_b = Project(user_id=alice_id, name="project-b")
    bob_project = Project(user_id=bob_id, name="bob-project")
    db.add_all([project_a, project_b, bob_project])
    db.flush()
    conversation = create_conversation(
        db, alice_id, ConversationCreate(title="agent", project_id=project_a.id)
    )
    visible = _index_agent_document(
        db,
        store,
        user_id=alice_id,
        filename="visible.txt",
        content="alpha visible",
        project_id=project_a.id,
    )
    _index_agent_document(
        db,
        store,
        user_id=alice_id,
        filename="other-project.txt",
        content="alpha other project",
        project_id=project_b.id,
    )
    _index_agent_document(
        db,
        store,
        user_id=bob_id,
        filename="other-user.txt",
        content="alpha other user",
        project_id=bob_project.id,
    )
    db.commit()
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    _call(
                        name="knowledge_search",
                        arguments='{"query": "alpha", "top_k": 5}',
                    )
                ]
            ),
            LLMResponse(content="final"),
        ]
    )

    list(
        run_agent(
            db,
            alice_id,
            conversation.id,
            "find project knowledge",
            _registry(KnowledgeSearchTool()),
            provider,
            None,
            2,
        )
    )

    tool_chunks = json.loads(provider.calls[1]["messages"][-1].content)
    assert [chunk["document_id"] for chunk in tool_chunks] == [visible.id]


def test_non_project_agent_knowledge_search_keeps_user_wide_scope(db, monkeypatch):
    store = _configure_real_rag(db, monkeypatch)
    alice_id = _create_user(db, "alice")
    bob_id = _create_user(db, "bob")
    project_a = Project(user_id=alice_id, name="project-a")
    project_b = Project(user_id=alice_id, name="project-b")
    bob_project = Project(user_id=bob_id, name="bob-project")
    db.add_all([project_a, project_b, bob_project])
    db.flush()
    conversation = _create_conversation(db, alice_id)
    visible_a = _index_agent_document(
        db,
        store,
        user_id=alice_id,
        filename="project-a.txt",
        content="alpha project a",
        project_id=project_a.id,
    )
    visible_b = _index_agent_document(
        db,
        store,
        user_id=alice_id,
        filename="project-b.txt",
        content="alpha project b",
        project_id=project_b.id,
    )
    _index_agent_document(
        db,
        store,
        user_id=bob_id,
        filename="other-user.txt",
        content="alpha other user",
        project_id=bob_project.id,
    )
    db.commit()
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    _call(
                        name="knowledge_search",
                        arguments='{"query": "alpha", "top_k": 5}',
                    )
                ]
            ),
            LLMResponse(content="final"),
        ]
    )

    list(
        run_agent(
            db,
            alice_id,
            conversation.id,
            "find all my knowledge",
            _registry(KnowledgeSearchTool()),
            provider,
            None,
            2,
        )
    )

    tool_chunks = json.loads(provider.calls[1]["messages"][-1].content)
    assert {chunk["document_id"] for chunk in tool_chunks} == {
        visible_a.id,
        visible_b.id,
    }


def test_agent_multiple_tool_calls_are_sequential_and_linked(db):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    tool = FakeTool()
    provider = FakeProvider(
        [
            LLMResponse(tool_calls=[_call("one"), _call("two")]),
            LLMResponse(content="final"),
        ]
    )

    events = list(
        run_agent(db, user_id, conversation.id, "hello", _registry(tool), provider, None, 3)
    )

    tool_events = [event for event in events if event.type in {"tool_start", "tool_result"}]
    assert [(event.type, event.tool_call_id) for event in tool_events] == [
        ("tool_start", "one"),
        ("tool_result", "one"),
        ("tool_start", "two"),
        ("tool_result", "two"),
    ]
    assert len(tool.calls) == 2


def test_agent_multiple_steps_first_tool_then_final(db):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    provider = FakeProvider(
        [LLMResponse(tool_calls=[_call()]), LLMResponse(content="finished")]
    )

    events = list(
        run_agent(
            db,
            user_id,
            conversation.id,
            "hello",
            _registry(FakeTool()),
            provider,
            None,
            2,
        )
    )

    assert [event.step for event in events if event.type == "agent_step"] == [1, 2]
    assert events[-1].type == "done"


def test_agent_max_steps_stops_without_assistant(db):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    provider = FakeProvider([LLMResponse(tool_calls=[_call()]) for _ in range(2)])

    events = list(
        run_agent(
            db,
            user_id,
            conversation.id,
            "hello",
            _registry(FakeTool()),
            provider,
            None,
            2,
        )
    )

    assert events[-1].type == "error"
    assert events[-1].code == "max_steps"
    assert db.execute(
        select(Message).where(
            Message.conversation_id == conversation.id, Message.role == "assistant"
        )
    ).scalars().all() == []


def test_agent_unknown_tool_is_fatal(db):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    provider = FakeProvider([LLMResponse(tool_calls=[_call(name="missing")])])

    events = list(
        run_agent(db, user_id, conversation.id, "hello", _registry(), provider, None, 2)
    )

    assert events[-1].code == "unknown_tool"


@pytest.mark.parametrize("arguments", ["not json", '{"value": -1}'])
def test_agent_invalid_tool_arguments_continue(db, arguments):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    provider = FakeProvider(
        [
            LLMResponse(tool_calls=[_call(arguments=arguments)]),
            LLMResponse(content="recovered"),
        ]
    )

    events = list(
        run_agent(
            db,
            user_id,
            conversation.id,
            "hello",
            _registry(FakeTool()),
            provider,
            None,
            2,
        )
    )

    assert next(event for event in events if event.type == "tool_result").success is False
    assert events[-1].type == "done"
    assert provider.calls[1]["messages"][-1].content == "工具参数无效"


@pytest.mark.parametrize(
    "tool",
    [
        FakeTool(result=ToolResult(success=False, error_code="bad", content="bad result")),
        FakeTool(error=RuntimeError("private stack detail")),
    ],
)
def test_agent_tool_failure_is_nonfatal(db, tool):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    provider = FakeProvider(
        [LLMResponse(tool_calls=[_call()]), LLMResponse(content="recovered")]
    )

    events = list(
        run_agent(db, user_id, conversation.id, "hello", _registry(tool), provider, None, 2)
    )

    result = next(event for event in events if event.type == "tool_result")
    assert result.success is False
    assert result.summary == "失败"
    assert events[-1].type == "done"


def test_agent_llm_error_propagates_without_persisted_messages(db):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    provider = FakeProvider([LLMError("provider failure")])

    with pytest.raises(LLMError):
        list(
            run_agent(db, user_id, conversation.id, "hello", _registry(), provider, None, 2)
        )

    db.rollback()
    assert db.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    ).scalars().all() == []


def test_agent_final_answer_persists_user_and_assistant(db):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)

    events = list(
        run_agent(
            db,
            user_id,
            conversation.id,
            "hello",
            _registry(),
            FakeProvider([LLMResponse(content="answer", model="final-model")]),
            None,
            2,
        )
    )

    done = events[-1]
    user_message = db.get(Message, done.user_message_id)
    assistant_message = db.get(Message, done.assistant_message_id)
    assert (user_message.role, user_message.content) == ("user", "hello")
    assert (assistant_message.role, assistant_message.content, assistant_message.model) == (
        "assistant",
        "answer",
        "final-model",
    )


def test_agent_failure_can_be_rolled_back_without_residual_messages(db):
    user_id = _create_user(db)
    conversation = _create_conversation(db, user_id)
    provider = FakeProvider([LLMResponse(tool_calls=[_call()]), LLMError("failure")])

    with pytest.raises(LLMError):
        list(
            run_agent(
                db,
                user_id,
                conversation.id,
                "hello",
                _registry(FakeTool()),
                provider,
                None,
                2,
            )
        )

    db.rollback()
    assert db.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    ).scalars().all() == []


def test_agent_service_has_no_commit_and_route_rolls_back_uncommitted_streams():
    assert ".commit(" not in inspect.getsource(run_agent)
    source = inspect.getsource(agent_route.agent_stream)
    assert source.count("db.commit()") == 1
    assert "finally:" in source
    assert "db.rollback()" in source
