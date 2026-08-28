from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.schemas.conversation import ConversationCreate, ConversationUpdate


def create_conversation(
    session: Session,
    user_id: int,
    data: ConversationCreate,
) -> Conversation:
    conversation = Conversation(
        user_id=user_id,
        title=data.title,
        model=data.model,
    )
    session.add(conversation)
    session.flush()
    session.refresh(conversation)
    return conversation


def list_conversations(
    session: Session,
    user_id: int,
) -> list[Conversation]:
    result = session.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    return list(result.scalars().all())


def get_conversation(
    session: Session,
    user_id: int,
    conversation_id: int,
) -> Conversation | None:
    result = session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


def update_conversation(
    session: Session,
    user_id: int,
    conversation_id: int,
    data: ConversationUpdate,
) -> Conversation | None:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        return None
    conversation.title = data.title
    session.flush()
    return conversation


def delete_conversation(
    session: Session,
    user_id: int,
    conversation_id: int,
) -> bool:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        return False
    session.delete(conversation)
    session.flush()
    return True
