import inspect

import pytest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.agent.base import Tool, ToolContext, ToolResult
from app.agent.loop import run_agent
from app.agent.registry import ToolRegistry
from app.api.routes import agent as agent_route
from app.llm.base import LLMError, LLMResponse, LLMToolCall
from app.models.message import Message
from app.models.user import User
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
