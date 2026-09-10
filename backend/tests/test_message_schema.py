import pytest
from pydantic import ValidationError

from app.schemas.message import MessageCreate


def test_content_ok():
    payload = MessageCreate(content="hello")

    assert payload.content == "hello"


def test_content_empty_rejected():
    with pytest.raises(ValidationError):
        MessageCreate(content="")


def test_extra_role_rejected():
    with pytest.raises(ValidationError):
        MessageCreate(content="hello", role="user")


def test_extra_conversation_id_rejected():
    with pytest.raises(ValidationError):
        MessageCreate(content="hello", conversation_id=1)
