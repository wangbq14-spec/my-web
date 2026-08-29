import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.base import ToolContext, ToolResult
from app.agent.registry import ToolRegistry
from app.llm.base import LLMMessage, LLMProvider
from app.models.message import Message
from app.models.user import utcnow_naive
from app.services.conversation import get_conversation
from app.services.title import maybe_auto_title


@dataclass
class AgentEvent:
    type: Literal[
        "not_found",
        "agent_step",
        "tool_start",
        "tool_result",
        "delta",
        "done",
        "error",
    ]
    step: int | None = None
    tool_call_id: str | None = None
    name: str | None = None
    success: bool | None = None
    summary: str | None = None
    content: str | None = None
    user_message_id: int | None = None
    assistant_message_id: int | None = None
    model: str | None = None
    code: str | None = None
    message: str | None = None


def run_agent(
    session: Session,
    user_id: int,
    conversation_id: int,
    content: str,
    registry: ToolRegistry,
    provider: LLMProvider,
    model: str | None,
    max_steps: int,
) -> Iterator[AgentEvent]:
    """Run a bounded, in-memory tool loop without committing the transaction."""

    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        yield AgentEvent(type="not_found")
        return

    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=content,
        model=None,
    )
    session.add(user_message)
    session.flush()
    session.refresh(user_message)

    history = (
        session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        .scalars()
        .all()
    )
    messages = [LLMMessage(role=message.role, content=message.content) for message in history]
    tools = registry.to_llm_schema()

    for step in range(1, max_steps + 1):
        yield AgentEvent(type="agent_step", step=step)
        response = provider.complete(messages, model=model, tools=tools)

        if response.tool_calls:
            messages.append(
                LLMMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )
            for tool_call in response.tool_calls:
                tool = registry.get(tool_call.name)
                if tool is None:
                    yield AgentEvent(
                        type="error",
                        code="unknown_tool",
                        message=f"未知工具：{tool_call.name}",
                    )
                    return

                try:
                    raw_arguments = json.loads(tool_call.arguments)
                    args = tool.input_schema.model_validate(raw_arguments)
                except (json.JSONDecodeError, ValueError):
                    result = ToolResult(
                        success=False,
                        error_code="invalid_arguments",
                        content="工具参数无效",
                    )
                else:
                    try:
                        result = tool.execute(
                            args,
                            ToolContext(user_id=user_id, session=session),
                        )
                    except Exception:
                        result = ToolResult(
                            success=False,
                            error_code="tool_error",
                            content="工具执行失败",
                        )

                yield AgentEvent(
                    type="tool_start",
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                )
                yield AgentEvent(
                    type="tool_result",
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                    success=result.success,
                    summary="完成" if result.success else "失败",
                )
                messages.append(
                    LLMMessage(
                        role="tool",
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                        content=result.content,
                    )
                )
            continue

        final_content = response.content or ""
        yield AgentEvent(type="delta", content=final_content)
        assistant_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=final_content,
            model=response.model,
        )
        session.add(assistant_message)
        session.flush()
        session.refresh(assistant_message)
        conversation.updated_at = utcnow_naive()
        session.flush()
        maybe_auto_title(conversation, content)
        yield AgentEvent(
            type="done",
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            model=assistant_message.model,
        )
        return

    yield AgentEvent(type="error", code="max_steps", message="达到最大步骤数")
