from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.conversation import ConversationCreate, ConversationOut


def test_default_title():
    payload = ConversationCreate()

    assert payload.title == "新对话"
    assert payload.model is None


def test_title_too_long_rejected():
    with pytest.raises(ValidationError):
        ConversationCreate(title="x" * 201)


def test_model_too_long_rejected():
    with pytest.raises(ValidationError):
        ConversationCreate(title="ok", model="x" * 101)


def test_conversation_out_from_orm_object():
    now = datetime(2025, 1, 1, 12, 0, 0)
    orm_obj = SimpleNamespace(
        id=1,
        title="hello",
        model=None,
        created_at=now,
        updated_at=now,
    )

    out = ConversationOut.model_validate(orm_obj)

    assert out.id == 1
    assert out.title == "hello"
    assert out.model is None
    assert out.created_at == now
    assert out.updated_at == now


def test_conversation_create_rejects_user_id():
    assert "user_id" not in ConversationCreate.model_fields

    with pytest.raises(ValidationError):
        ConversationCreate(title="hi", user_id=999)


def test_conversation_create_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ConversationCreate(title="hi", unexpected="value")
