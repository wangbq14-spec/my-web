from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message
from app.schemas.message import MessageCreate
from app.services.conversation import get_conversation


def create_user_message(
    session: Session,
    user_id: int,
    conversation_id: int,
    data: MessageCreate,
) -> Message | None:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        return None

    message = Message(
        conversation_id=conversation_id,
        role="user",
        content=data.content,
        model=None,
    )
    session.add(message)
    session.flush()
    session.refresh(message)
    return message


def list_messages(
    session: Session,
    user_id: int,
    conversation_id: int,
) -> list[Message] | None:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        return None

    result = session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return list(result.scalars().all())
