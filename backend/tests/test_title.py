from datetime import datetime

import pytest

from app.agent.loop import run_agent
from app.agent.registry import ToolRegistry
from app.llm.base import LLMChunk, LLMError, LLMResponse
from app.models.conversation import Conversation
from app.models.user import User
from app.schemas.conversation import ConversationCreate
from app.services import chat
from app.services.chat import send_chat_message, stream_chat_message
from app.services.conversation import create_conversation, list_conversations
from app.services.title import DEFAULT_TITLE, generate_title


class FakeCompletionProvider:
    def __init__(self, response=None, error=None):
        self.response = response or LLMResponse(content="answer", model="fake-model")
        self.error = error

    def complete(self, messages, *, model=None, tools=None):
        if self.error is not None:
            raise self.error
        return self.response


class FakeStreamProvider:
    def stream(self, messages, *, model=None):
        yield LLMChunk(content="answer", model="fake-stream-model")


def _create_user(db, username="alice"):
    user = User(email=f"{username}@example.com", username=username, hashed_password="x")
    db.add(user)
    db.flush()
    return user.id


def _create_default_conversation(db, user_id):
    return create_conversation(db, user_id, ConversationCreate())


def test_default_title_matches_conversation_defaults(db):
    user_id = _create_user(db)
    conversation = _create_default_conversation(db, user_id)

    assert DEFAULT_TITLE == "新对话"
    assert ConversationCreate().title == DEFAULT_TITLE
    assert conversation.title == DEFAULT_TITLE


def test_generate_title_normalizes_redacts_and_truncates():
    content = "标题内容" * 20

    assert generate_title("  多个\n\t空白  ") == "多个 空白"
    assert generate_title(content) == f"{content[:30]}…"
    assert generate_title("sk-abcdefghijklmnopqrstuvwxyz123456 Bearer topsecret token=moresecret api key=lastsecret") == DEFAULT_TITLE


@pytest.mark.parametrize(
    "content, secret",
    [
        ("secret=my-prod-key", "my-prod-key"),
        ("password=p@ss", "p@ss"),
        ("token abc123", "abc123"),
        ("key=k", "k"),
        ("client_secret=client-prod-secret", "client-prod-secret"),
        ("credential=service-credential", "service-credential"),
    ],
)
def test_first_chat_title_redacts_additional_secret_formats(db, monkeypatch, content, secret):
    user_id = _create_user(db)
    conversation = _create_default_conversation(db, user_id)
    monkeypatch.setattr(chat, "get_llm_provider", lambda: FakeCompletionProvider())

    send_chat_message(db, user_id, conversation.id, content)

    assert secret not in conversation.title
    assert conversation.title == DEFAULT_TITLE or "[REDACTED]" in conversation.title


def test_first_successful_chat_auto_titles_conversation(db, monkeypatch):
    user_id = _create_user(db)
    conversation = _create_default_conversation(db, user_id)
    monkeypatch.setattr(chat, "get_llm_provider", lambda: FakeCompletionProvider())

    send_chat_message(db, user_id, conversation.id, "帮我规划周末旅行")

    assert conversation.title == "帮我规划周末旅行"


def test_failed_chat_rollback_keeps_default_title(db, monkeypatch):
    user_id = _create_user(db)
    conversation = _create_default_conversation(db, user_id)
    db.commit()
    monkeypatch.setattr(
        chat, "get_llm_provider", lambda: FakeCompletionProvider(error=LLMError("boom"))
    )

    with pytest.raises(LLMError):
        send_chat_message(db, user_id, conversation.id, "不会成为标题")

    db.rollback()
    assert db.get(Conversation, conversation.id).title == DEFAULT_TITLE


def test_rag_chat_auto_titles_conversation(db, monkeypatch):
    user_id = _create_user(db)
    conversation = _create_default_conversation(db, user_id)
    monkeypatch.setattr(chat, "get_llm_provider", lambda: FakeCompletionProvider())
    monkeypatch.setattr(chat, "retrieve", lambda *args: [])

    send_chat_message(db, user_id, conversation.id, "总结这份知识库", use_rag=True)

    assert conversation.title == "总结这份知识库"


def test_stream_chat_auto_titles_conversation(db, monkeypatch):
    user_id = _create_user(db)
    conversation = _create_default_conversation(db, user_id)
    monkeypatch.setattr(chat, "get_llm_provider", lambda: FakeStreamProvider())

    events = list(stream_chat_message(db, user_id, conversation.id, "流式标题测试"))

    assert events[-1].type == "done"
    assert conversation.title == "流式标题测试"


def test_agent_auto_titles_conversation(db):
    user_id = _create_user(db)
    conversation = _create_default_conversation(db, user_id)

    events = list(
        run_agent(
            db,
            user_id,
            conversation.id,
            "Agent 标题测试",
            ToolRegistry(),
            FakeCompletionProvider(),
            None,
            2,
        )
    )

    assert events[-1].type == "done"
    assert conversation.title == "Agent 标题测试"


def test_title_does_not_contain_secrets_or_tokens(db, monkeypatch):
    user_id = _create_user(db)
    conversation = _create_default_conversation(db, user_id)
    monkeypatch.setattr(chat, "get_llm_provider", lambda: FakeCompletionProvider())

    send_chat_message(
        db,
        user_id,
        conversation.id,
        "请帮我检查 sk-abcdefghijklmnopqrstuvwxyz123456 Bearer topsecret token=moresecret api key=lastsecret",
    )

    title = conversation.title.lower()
    assert title == "请帮我检查"
    assert all(secret not in title for secret in ("sk-", "bearer", "token", "api key", "secret"))


def test_successful_chat_updates_timestamp_and_moves_conversation_to_top(db, monkeypatch):
    user_id = _create_user(db)
    conversation = _create_default_conversation(db, user_id)
    other = _create_default_conversation(db, user_id)
    conversation.updated_at = datetime(2020, 1, 1)
    db.commit()
    monkeypatch.setattr(chat, "get_llm_provider", lambda: FakeCompletionProvider())

    send_chat_message(db, user_id, conversation.id, "置顶会话")
    db.commit()

    refreshed = db.get(Conversation, conversation.id)
    assert refreshed.updated_at > datetime(2020, 1, 1)
    assert list_conversations(db, user_id)[0].id == conversation.id
    assert other.id != conversation.id
