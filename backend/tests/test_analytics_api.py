"""Admin Beta analytics API contracts. DSH runs these tests."""

import pytest

from app.core.security import create_access_token
from app.models.beta import Feedback
from app.models.billing import UsageRecord
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User


@pytest.fixture()
def actors(db):
    admin = User(username="admin", email="admin@example.com",
                 hashed_password="unused", role="admin")
    alice = User(username="alice", email="alice@example.com",
                 hashed_password="unused", role="user")
    db.add_all([admin, alice])
    db.commit()
    return {
        "admin": (admin.id, {"Authorization": f"Bearer {create_access_token(str(admin.id))}"}),
        "user": (alice.id, {"Authorization": f"Bearer {create_access_token(str(alice.id))}"}),
    }


def test_analytics_rejects_ordinary_users(client, actors):
    response = client.get("/api/admin/analytics", headers=actors["user"][1])
    assert response.status_code == 403


def test_analytics_overview_counts_and_no_content_leak(client, db, actors):
    alice_id, _ = actors["user"]
    conversation = Conversation(user_id=alice_id)
    db.add(conversation)
    db.flush()
    db.add(Message(conversation_id=conversation.id, role="user", content="secret prompt abc"))
    db.add(UsageRecord(user_id=alice_id, provider="test", model="test", model_tier="standard",
                       prompt_tokens=1, completion_tokens=1, total_tokens=2,
                       estimated_cost=0.0, credits_charged=1, request_id="usage-analytics-1"))
    db.add(Feedback(user_id=alice_id, type="bug", path="/chat", message="report something"))
    db.commit()

    response = client.get("/api/admin/analytics", headers=actors["admin"][1])
    assert response.status_code == 200
    data = response.json()

    expected_keys = {
        "registered", "active_users", "new_users", "chat_messages", "rag_chunks",
        "agent_steps", "workflows", "documents", "projects", "credits",
        "model_tier", "feedback", "range",
    }
    assert set(data.keys()) == expected_keys

    assert data["range"] == "7d"
    assert data["registered"] == 2
    assert data["active_users"] == 1
    assert data["new_users"] == 2
    assert data["chat_messages"] == 1
    assert data["rag_chunks"] == 0
    assert data["agent_steps"] == 0
    assert data["workflows"] == 0
    assert data["documents"] == 0
    assert data["projects"] == 0
    assert data["credits"] == {"granted": 0, "consumed": 0}
    assert data["model_tier"] == {"standard": 1}
    assert data["feedback"] == 1

    assert "secret prompt abc" not in response.text


def test_analytics_rejects_bogus_range(client, actors):
    response = client.get("/api/admin/analytics", headers=actors["admin"][1],
                          params={"range": "bogus"})
    assert response.status_code == 422
