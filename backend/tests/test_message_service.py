from datetime import datetime

from app.models.user import User
from app.schemas.conversation import ConversationCreate
from app.schemas.message import MessageCreate
from app.services.conversation import create_conversation
from app.services.message import create_user_message, list_messages


def _create_user(db, username: str) -> int:
    user = User(
        email=f"{username}@example.com",
        username=username,
        hashed_password="x",
    )
    db.add(user)
    db.flush()
    return user.id


def _create_conversation(db, user_id: int):
    return create_conversation(db, user_id, ConversationCreate(title="c1"))


def test_create_user_message_success(db):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)

    msg = create_user_message(db, user_id, conv.id, MessageCreate(content="你好"))

    assert msg is not None
    assert msg.content == "你好"
    assert msg.conversation_id == conv.id


def test_message_role_is_user(db):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)

    msg = create_user_message(db, user_id, conv.id, MessageCreate(content="hi"))

    assert msg.role == "user"


def test_conversation_id_from_service_not_schema(db):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)

    data = MessageCreate(content="hi")
    msg = create_user_message(db, user_id, conv.id, data)

    assert msg.conversation_id == conv.id


def test_create_message_on_other_users_conversation_returns_none(db):
    user_a = _create_user(db, "alice")
    user_b = _create_user(db, "bob")
    conv_b = _create_conversation(db, user_b)

    msg = create_user_message(db, user_a, conv_b.id, MessageCreate(content="hi"))

    assert msg is None


def test_list_messages_own(db):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)
    create_user_message(db, user_id, conv.id, MessageCreate(content="m1"))
    create_user_message(db, user_id, conv.id, MessageCreate(content="m2"))

    result = list_messages(db, user_id, conv.id)

    assert result is not None
    assert [m.content for m in result] == ["m1", "m2"]


def test_list_messages_other_users_returns_none(db):
    user_a = _create_user(db, "alice")
    user_b = _create_user(db, "bob")
    conv_b = _create_conversation(db, user_b)

    result = list_messages(db, user_a, conv_b.id)

    assert result is None


def test_list_messages_sorted_asc(db):
    user_id = _create_user(db, "alice")
    conv = _create_conversation(db, user_id)

    m1 = create_user_message(db, user_id, conv.id, MessageCreate(content="m1"))
    m2 = create_user_message(db, user_id, conv.id, MessageCreate(content="m2"))
    m3 = create_user_message(db, user_id, conv.id, MessageCreate(content="m3"))

    m1.created_at = datetime(2025, 1, 1, 8, 0, 0)
    m2.created_at = datetime(2025, 1, 2, 8, 0, 0)
    m3.created_at = datetime(2025, 1, 2, 8, 0, 0)
    db.flush()

    result = list_messages(db, user_id, conv.id)

    assert [m.content for m in result] == ["m1", "m2", "m3"]
