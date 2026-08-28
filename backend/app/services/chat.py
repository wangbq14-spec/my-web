from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.base import LLMMessage
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
