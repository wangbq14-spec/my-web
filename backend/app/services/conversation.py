from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.project import Project
from app.schemas.conversation import ConversationCreate, ConversationUpdate
from app.services.project import touch_project_activity


class ProjectNotFoundError(Exception):
    """Raised when a project is missing or belongs to another user."""


def _ensure_owned_project(session: Session, user_id: int, project_id: int) -> None:
    project = session.scalar(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    if project is None:
        raise ProjectNotFoundError


def create_conversation(
    session: Session,
    user_id: int,
    data: ConversationCreate,
) -> Conversation:
    if data.project_id is not None:
        _ensure_owned_project(session, user_id, data.project_id)

    conversation = Conversation(
        user_id=user_id,
        title=data.title,
        model=data.model,
        project_id=data.project_id,
    )
    session.add(conversation)
    session.flush()
    if data.project_id is not None:
        touch_project_activity(session, data.project_id)
    session.refresh(conversation)
    return conversation


def list_conversations(
    session: Session,
    user_id: int,
    project_id: int | None = None,
) -> list[Conversation]:
    conditions = [Conversation.user_id == user_id]
    if project_id is not None:
        conditions.append(Conversation.project_id == project_id)
    result = session.execute(
        select(Conversation)
        .where(*conditions)
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
    fields = data.model_fields_set
    original_project_id = conversation.project_id
    if "title" in fields:
        conversation.title = data.title
    if "project_id" in fields:
        if data.project_id is not None:
            _ensure_owned_project(session, user_id, data.project_id)
        conversation.project_id = data.project_id
    session.flush()
    project_ids_to_touch: set[int] = set()
    if "title" in fields and original_project_id is not None:
        project_ids_to_touch.add(original_project_id)
    if "project_id" in fields:
        if original_project_id is not None:
            project_ids_to_touch.add(original_project_id)
        if data.project_id is not None:
            project_ids_to_touch.add(data.project_id)
    for project_id in project_ids_to_touch:
        touch_project_activity(session, project_id)
    return conversation


def delete_conversation(
    session: Session,
    user_id: int,
    conversation_id: int,
) -> bool:
    conversation = get_conversation(session, user_id, conversation_id)
    if conversation is None:
        return False
    original_project_id = conversation.project_id
    session.delete(conversation)
    session.flush()
    if original_project_id is not None:
        touch_project_activity(session, original_project_id)
    return True
