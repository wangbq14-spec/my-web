from datetime import datetime

from app.models.user import User
from app.schemas.conversation import ConversationCreate
from app.services.conversation import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
)


def _create_user(db, username: str) -> int:
    user = User(
        email=f"{username}@example.com",
        username=username,
        hashed_password="x",
    )
    db.add(user)
    db.flush()
    return user.id


def test_create_conversation_success(db):
    user_id = _create_user(db, "alice")

    conv = create_conversation(
        db, user_id, ConversationCreate(title="我的会话", model="gpt-x")
    )

    assert conv.id is not None
    assert conv.user_id == user_id
    assert conv.title == "我的会话"
    assert conv.model == "gpt-x"


def test_create_uses_service_user_id_not_schema(db):
    user_id = _create_user(db, "alice")
    data = ConversationCreate(title="hi")

    conv = create_conversation(db, user_id, data)

    assert conv.user_id == user_id


def test_list_only_own_conversations(db):
    user_a = _create_user(db, "alice")
    user_b = _create_user(db, "bob")

    create_conversation(db, user_a, ConversationCreate(title="A1"))
    create_conversation(db, user_b, ConversationCreate(title="B1"))

    result = list_conversations(db, user_a)

    assert [c.title for c in result] == ["A1"]
    assert all(c.user_id == user_a for c in result)


def test_get_own_conversation(db):
    user_a = _create_user(db, "alice")
    conv = create_conversation(db, user_a, ConversationCreate(title="A1"))

    found = get_conversation(db, user_a, conv.id)

    assert found is not None
    assert found.id == conv.id


def test_get_other_users_conversation_returns_none(db):
    user_a = _create_user(db, "alice")
    user_b = _create_user(db, "bob")
    conv_b = create_conversation(db, user_b, ConversationCreate(title="B1"))

    found = get_conversation(db, user_a, conv_b.id)

    assert found is None


def test_delete_own_conversation(db):
    user_a = _create_user(db, "alice")
    conv = create_conversation(db, user_a, ConversationCreate(title="A1"))
    conv_id = conv.id

    assert delete_conversation(db, user_a, conv_id) is True

    assert get_conversation(db, user_a, conv_id) is None


def test_delete_other_users_conversation_returns_false(db):
    user_a = _create_user(db, "alice")
    user_b = _create_user(db, "bob")
    conv_b = create_conversation(db, user_b, ConversationCreate(title="B1"))

    assert delete_conversation(db, user_a, conv_b.id) is False

    assert get_conversation(db, user_b, conv_b.id) is not None


def test_list_sorted_by_updated_at_desc_and_id_desc(db):
    user_a = _create_user(db, "alice")

    c1 = create_conversation(db, user_a, ConversationCreate(title="c1"))
    c2 = create_conversation(db, user_a, ConversationCreate(title="c2"))
    c3 = create_conversation(db, user_a, ConversationCreate(title="c3"))

    c1.updated_at = datetime(2025, 1, 1, 8, 0, 0)
    c2.updated_at = datetime(2025, 1, 2, 8, 0, 0)
    c3.updated_at = datetime(2025, 1, 2, 8, 0, 0)
    db.flush()

    result = list_conversations(db, user_a)

    assert [c.title for c in result] == ["c3", "c2", "c1"]
