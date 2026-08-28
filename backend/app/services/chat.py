from dataclasses import dataclass
from typing import Iterator, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.base import LLMError, LLMMessage
from app.llm.factory import get_llm_provider
from app.models.message import Message
from app.models.user import utcnow_naive
from app.services.conversation import get_conversation


@dataclass
class ChatResult:
    user_message: Message
    assistant_message: Message


def send_chat_message(
    session: Session,
    user_id: int,
    conversation_id: int,
    content: str,
) -> ChatResult | None:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        return None

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

    llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]

    provider = get_llm_provider()
    response = provider.complete(llm_messages, model=conversation.model)

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=response.content,
        model=response.model,
    )
    session.add(assistant_message)
    session.flush()
    session.refresh(assistant_message)

    conversation.updated_at = utcnow_naive()
    session.flush()

    return ChatResult(user_message=user_message, assistant_message=assistant_message)


@dataclass
class StreamEvent:
    type: Literal["delta", "done", "not_found", "no_user_message"]
    content: str | None = None
    user_message_id: int | None = None
    assistant_message_id: int | None = None
    model: str | None = None


def stream_chat_message(
    session: Session,
    user_id: int,
    conversation_id: int,
    content: str,
) -> Iterator[StreamEvent]:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        yield StreamEvent(type="not_found")
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

    llm_messages = [LLMMessage(role=m.role, content=m.content) for m in history]

    provider = get_llm_provider()

    chunks: list[str] = []
    actual_model: str | None = None
    for chunk in provider.stream(llm_messages, model=conversation.model):
        if chunk.content:
            chunks.append(chunk.content)
            if chunk.model:
                actual_model = chunk.model
            yield StreamEvent(type="delta", content=chunk.content)

    full_content = "".join(chunks)
    if not full_content.strip():
        raise LLMError("上游返回空内容")

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_content,
        model=actual_model or conversation.model,
    )
    session.add(assistant_message)
    session.flush()
    session.refresh(assistant_message)

    conversation.updated_at = utcnow_naive()
    session.flush()

    yield StreamEvent(
        type="done",
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        model=assistant_message.model,
    )


def regenerate_chat_message(
    session: Session,
    user_id: int,
    conversation_id: int,
) -> Iterator[StreamEvent]:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        yield StreamEvent(type="not_found")
        return

    messages = (
        session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        .scalars()
        .all()
    )
    last_user_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if messages[index].role == "user"),
        None,
    )
    if last_user_index is None:
        yield StreamEvent(type="no_user_message")
        return

    context = messages[: last_user_index + 1]
    llm_messages = [LLMMessage(role=message.role, content=message.content) for message in context]
    provider = get_llm_provider()

    chunks: list[str] = []
    actual_model: str | None = None
    for chunk in provider.stream(llm_messages, model=conversation.model):
        if chunk.content:
            chunks.append(chunk.content)
            if chunk.model:
                actual_model = chunk.model
            yield StreamEvent(type="delta", content=chunk.content)

    full_content = "".join(chunks)
    if not full_content.strip():
        raise LLMError("上游返回空内容")

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=full_content,
        model=actual_model or conversation.model,
    )
    session.add(assistant_message)
    session.flush()
    session.refresh(assistant_message)

    conversation.updated_at = utcnow_naive()
    session.flush()

    yield StreamEvent(
        type="done",
        assistant_message_id=assistant_message.id,
        model=assistant_message.model,
    )
