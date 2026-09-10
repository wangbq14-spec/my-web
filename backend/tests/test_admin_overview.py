"""Admin Operations Center: overview aggregation, health, and user filters."""

from datetime import timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.beta import Feedback, RechargeRequest
from app.models.billing import CreditLedger, UsageRecord, UserWallet
from app.models.document import Document
from app.models.rag_query import RagQuery
from app.models.user import User, utcnow_naive
from app.services import billing


@pytest.fixture()
def actors(db):
    users = [User(username=name, email=f"{name}@example.com", hashed_password="unused",
                  role=role) for name, role in [("admin", "admin"), ("alice", "user"), ("bob", "user")]]
    db.add_all(users)
    db.commit()
    return [(u.id, {"Authorization": f"Bearer {create_access_token(subject=str(u.id))}"}) for u in users]


def _usage(db, uid, kind, request_id, credits=1):
    db.add(UsageRecord(user_id=uid, provider="mock", model="m", model_tier="standard",
                       prompt_tokens=10, completion_tokens=10, total_tokens=20,
                       estimated_cost=0.001, credits_charged=credits,
                       request_id=request_id, kind=kind))


def test_overview_requires_admin(client, actors):
    assert client.get("/api/admin/overview", headers=actors[1][1]).status_code == 403
    assert client.get("/api/admin/users?filter=active", headers=actors[1][1]).status_code == 403


def test_overview_today_metrics(client, db, actors):
    admin_id, _ = actors[0]
    alice_id, _ = actors[1]
    bob_id, _ = actors[2]

    # Activity "today" (created_at defaults to now): chat x3, vision x1, agent x1.
    for i in range(3):
        _usage(db, alice_id, "chat", f"today-chat-{i}")
    _usage(db, alice_id, "vision", "today-vision", credits=2)
    _usage(db, bob_id, "agent", "today-agent")
    db.add(CreditLedger(user_id=alice_id, amount=-5, operation="consume",
                        request_id="c1", description="chat"))
    # RAG retrievals.
    db.add_all([RagQuery(user_id=alice_id), RagQuery(user_id=alice_id)])
    # Documents uploaded today.
    for status in ("ready", "failed"):
        db.add(Document(user_id=alice_id, filename=f"{status}.txt", original_filename=f"{status}.txt",
                        file_size=10, status=status))
    # One pending + one approved recharge.
    db.add(RechargeRequest(user_id=alice_id, package_code="experience", amount_display="10 CNY",
                           credits_requested=1000, status="pending"))
    db.add(RechargeRequest(user_id=bob_id, package_code="experience", amount_display="10 CNY",
                           credits_requested=1000, status="approved"))
    # Feedback: one new, one reviewed.
    db.add(Feedback(user_id=alice_id, type="bug", path="/chat", message="x", status="new"))
    db.add(Feedback(user_id=bob_id, type="suggestion", path="/usage", message="y", status="reviewed"))
    db.commit()

    response = client.get("/api/admin/overview", headers=actors[0][1])
    assert response.status_code == 200
    data = response.json()

    today = data["today"]
    assert today["new_users"] >= 3
    assert today["active_users"] >= 2
    assert today["chat_requests"] == 3
    assert today["rag_requests"] == 2
    assert today["agent_requests"] == 1
    assert today["vision_requests"] == 1
    assert today["documents_uploaded"] == 2
    assert today["credits_consumed"] == 5
    assert today["pending_recharge_requests"] == 1
    assert today["new_feedback"] == 2
    assert today["unreviewed_feedback"] == 1

    last_7d = data["last_7d"]
    assert last_7d["total_ai_requests"] >= 5
    assert last_7d["credits_consumed"] == 5
    assert last_7d["most_used_model_tier"] == "standard"
    assert last_7d["vision_usage"]["requests"] == 1
    assert last_7d["vision_usage"]["credits"] == 2
    assert last_7d["rag_usage"] == 2

    health = data["health"]
    assert health["active_users"] >= 2
    assert health["document_success_rate"] == pytest.approx(0.5)
    # Not derivable from the current data model -> explicitly deferred, never guessed.
    assert health["ai_success_rate"] is None
    assert health["ai_error_rate"] is None
    assert health["vision_success_rate"] is None
    assert data["generated_at"]


def test_overview_returning_users(client, db, actors):
    admin_id, _ = actors[0]
    old = User(username="old", email="old@example.com", hashed_password="unused", role="user",
               created_at=utcnow_naive() - timedelta(days=10))
    db.add(old)
    db.commit()
    _usage(db, old.id, "chat", "old-usage")
    db.commit()

    data = client.get("/api/admin/overview", headers=actors[0][1]).json()
    assert data["health"]["returning_users"] >= 1


def test_users_filters_and_last_active(client, db, actors):
    admin_id, _ = actors[0]
    alice_id, bob_id = actors[1][0], actors[2][0]
    db.add(UserWallet(user_id=alice_id, balance=500))
    db.add(UserWallet(user_id=bob_id, balance=10))
    _usage(db, alice_id, "chat", "filter-usage")
    db.commit()

    headers = actors[0][1]
    active = client.get("/api/admin/users?filter=active", headers=headers).json()
    assert all(u["is_active"] for u in active)

    low = client.get("/api/admin/users?filter=low_balance", headers=headers).json()
    low_ids = {u["id"] for u in low}
    assert bob_id in low_ids and alice_id not in low_ids

    new = client.get("/api/admin/users?filter=new", headers=headers).json()
    assert {u["id"] for u in new} >= {alice_id, bob_id}

    summary = next(u for u in client.get("/api/admin/users", headers=headers).json() if u["id"] == alice_id)
    assert summary["last_active_at"] is not None
    # Sensitive fields never exposed.
    for key in ("hashed_password", "email_secret", "jwt"):
        assert key not in summary


def test_rag_query_row_written_on_search(client, db, actors, monkeypatch):
    alice_id, alice_headers = actors[1]
    before = db.scalar(select(RagQuery.id).where(RagQuery.user_id == alice_id))
    assert before is None
    # The /search route needs embeddings + vector store; fake both so the test
    # only asserts the analytics row is recorded regardless of retrieval hits.
    monkeypatch.setattr("app.api.routes.retrieval.retrieve", lambda *a, **k: [])
    response = client.post("/api/retrieval/search", headers=alice_headers,
                           json={"query": "anything", "top_k": 3})
    assert response.status_code == 200
    assert db.scalar(select(RagQuery.id).where(RagQuery.user_id == alice_id)) is not None
