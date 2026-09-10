"""Feedback API contracts. DSH runs these tests."""

import pytest

from app.core.security import create_access_token
from app.models.user import User


@pytest.fixture()
def actors(db):
    users = [User(username=name, email=f"{name}@example.com", hashed_password="unused",
                  role=role) for name, role in [("admin", "admin"), ("alice", "user"), ("bob", "user")]]
    db.add_all(users)
    db.commit()
    return [(u.id, {"Authorization": f"Bearer {create_access_token(subject=str(u.id))}"}) for u in users]


def submit(client, headers, **overrides):
    payload = {"type": "bug", "path": "/chat", "message": "hello"}
    payload.update(overrides)
    return client.post("/api/feedback", headers=headers, json=payload)


def test_submit_feedback_returns_new(client, actors):
    response = submit(client, actors[1][1])
    assert response.status_code == 201
    assert response.json()["status"] == "new"


def test_feedback_ownership(client, actors):
    item = submit(client, actors[1][1]).json()
    assert client.get("/api/feedback", headers=actors[1][1]).json() == [item]
    assert client.get("/api/feedback", headers=actors[2][1]).json() == []


def test_admin_lists_and_filters(client, actors):
    submit(client, actors[1][1])
    submit(client, actors[2][1])
    headers = actors[0][1]
    assert len(client.get("/api/admin/feedback", headers=headers).json()) == 2
    assert len(client.get("/api/admin/feedback?status=new", headers=headers).json()) == 2
    assert len(client.get("/api/admin/feedback?type=bug", headers=headers).json()) == 2


def test_admin_feedback_rejects_ordinary_users(client, actors):
    assert client.get("/api/admin/feedback", headers=actors[1][1]).status_code == 403
    assert client.post("/api/admin/feedback/1/status", headers=actors[1][1],
                       json={"status": "reviewed"}).status_code == 403


def test_feedback_rejects_long_and_empty_message(client, actors):
    assert submit(client, actors[1][1], message="x" * 10001).status_code == 422
    assert submit(client, actors[1][1], message="").status_code == 422


def test_admin_updates_status(client, actors):
    item = submit(client, actors[1][1]).json()
    headers = actors[0][1]
    url = f"/api/admin/feedback/{item['id']}/status"
    response = client.post(url, headers=headers, json={"status": "reviewed"})
    assert response.status_code == 200
    assert response.json()["status"] == "reviewed"
    assert client.post(url, headers=headers, json={"status": "bogus"}).status_code == 422
    assert client.post("/api/admin/feedback/9999/status", headers=headers,
                       json={"status": "reviewed"}).status_code == 404
