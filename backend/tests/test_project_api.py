from datetime import datetime

from app.api.routes import documents
from app.models.project import Project
from app.services.document_tasks import FakeDocumentTaskDispatcher


def _register_and_login(client, username: str) -> str:
    client.post(
        "/api/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "secret123",
        },
    )
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_project(client, token: str, **data):
    payload = {"name": "项目"}
    payload.update(data)
    return client.post("/api/projects", json=payload, headers=_auth(token))


def _upload(client, token: str, filename: str, project_id: int | None = None):
    data = {"project_id": str(project_id)} if project_id is not None else None
    return client.post(
        "/api/documents",
        files={"file": (filename, b"project document", "text/plain")},
        data=data,
        headers=_auth(token),
    )


def test_project_crud(client):
    token = _register_and_login(client, "alice")

    created = _create_project(
        client,
        token,
        name="研究计划",
        description="初始描述",
        instructions="初始指令",
    )
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "研究计划"
    assert project["description"] == "初始描述"
    assert project["instructions"] == "初始指令"
    assert project["pinned"] is False
    assert "user_id" not in project

    listed = client.get("/api/projects", headers=_auth(token))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [project["id"]]

    detail = client.get(f"/api/projects/{project['id']}", headers=_auth(token))
    assert detail.status_code == 200
    assert detail.json()["name"] == "研究计划"

    renamed = client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "新计划"},
        headers=_auth(token),
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "新计划"
    assert renamed.json()["description"] == "初始描述"

    updated = client.patch(
        f"/api/projects/{project['id']}",
        json={"description": "新描述", "instructions": "新指令"},
        headers=_auth(token),
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "新描述"
    assert updated.json()["instructions"] == "新指令"

    pinned = client.patch(
        f"/api/projects/{project['id']}",
        json={"description": "", "pinned": True},
        headers=_auth(token),
    )
    assert pinned.status_code == 200
    assert pinned.json()["description"] == ""
    assert pinned.json()["pinned"] is True

    deleted = client.delete(f"/api/projects/{project['id']}", headers=_auth(token))
    assert deleted.status_code == 204
    assert client.get(f"/api/projects/{project['id']}", headers=_auth(token)).status_code == 404


def test_project_ownership_is_hidden(client):
    alice = _register_and_login(client, "alice")
    bob = _register_and_login(client, "bob")
    project = _create_project(client, alice, name="Alice 的项目").json()
    path = f"/api/projects/{project['id']}"

    assert client.get(path, headers=_auth(bob)).status_code == 404
    assert client.patch(path, json={"pinned": True}, headers=_auth(bob)).status_code == 404
    assert client.delete(path, headers=_auth(bob)).status_code == 404


def test_project_requires_authentication_and_valid_payload(client):
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/projects", json={"name": "x"}).status_code == 401

    token = _register_and_login(client, "alice")
    assert _create_project(client, token, name="").status_code == 422
    assert _create_project(client, token, name="   ").status_code == 422
    assert client.post(
        "/api/projects", json={"name": "x", "user_id": 1}, headers=_auth(token)
    ).status_code == 422

    project = _create_project(client, token).json()
    assert client.patch(
        f"/api/projects/{project['id']}", json={}, headers=_auth(token)
    ).status_code == 422
    assert client.patch(
        f"/api/projects/{project['id']}",
        json={"unknown": "value"},
        headers=_auth(token),
    ).status_code == 422


def test_project_association_lists_and_missing_project(client, monkeypatch):
    monkeypatch.setattr(
        documents, "get_document_task_dispatcher", lambda: FakeDocumentTaskDispatcher()
    )
    token = _register_and_login(client, "alice")
    project = _create_project(client, token, name="归属项目").json()
    conversation = client.post(
        "/api/conversations",
        json={"title": "项目会话", "project_id": project["id"]},
        headers=_auth(token),
    ).json()
    client.post("/api/conversations", json={"title": "独立会话"}, headers=_auth(token))
    document = _upload(client, token, "project.txt").json()
    client.patch(
        f"/api/documents/{document['id']}",
        json={"project_id": project["id"]},
        headers=_auth(token),
    )

    conversations = client.get(
        f"/api/projects/{project['id']}/conversations", headers=_auth(token)
    )
    assert conversations.status_code == 200
    assert [item["id"] for item in conversations.json()] == [conversation["id"]]

    project_documents = client.get(
        f"/api/projects/{project['id']}/documents", headers=_auth(token)
    )
    assert project_documents.status_code == 200
    assert [item["id"] for item in project_documents.json()] == [document["id"]]

    assert client.get("/api/projects/999999/conversations", headers=_auth(token)).status_code == 404
    assert client.get("/api/projects/999999/documents", headers=_auth(token)).status_code == 404


def test_conversation_project_create_move_unassign_and_filter(client):
    token = _register_and_login(client, "alice")
    project = _create_project(client, token).json()
    other = _create_project(client, token, name="另一个项目").json()

    created = client.post(
        "/api/conversations",
        json={"title": "待归属", "project_id": project["id"]},
        headers=_auth(token),
    )
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["project_id"] == project["id"]
    assert conversation["pinned"] is False

    pinned = client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"pinned": True},
        headers=_auth(token),
    )
    assert pinned.status_code == 200
    assert pinned.json()["pinned"] is True

    filtered = client.get(
        f"/api/conversations?project_id={project['id']}", headers=_auth(token)
    )
    assert [item["id"] for item in filtered.json()] == [conversation["id"]]

    moved = client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"project_id": other["id"]},
        headers=_auth(token),
    )
    assert moved.status_code == 200
    assert moved.json()["project_id"] == other["id"]

    unassigned = client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"project_id": None},
        headers=_auth(token),
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["project_id"] is None
    assert client.patch(
        f"/api/conversations/{conversation['id']}", json={}, headers=_auth(token)
    ).status_code == 422
    assert client.get("/api/conversations?project_id=999999", headers=_auth(token)).status_code == 404


def test_project_assignment_rejects_another_users_project(client, monkeypatch):
    monkeypatch.setattr(
        documents, "get_document_task_dispatcher", lambda: FakeDocumentTaskDispatcher()
    )
    alice = _register_and_login(client, "alice")
    bob = _register_and_login(client, "bob")
    bob_project = _create_project(client, bob).json()
    conversation = client.post(
        "/api/conversations", json={"title": "Alice"}, headers=_auth(alice)
    ).json()
    document = _upload(client, alice, "alice.txt").json()

    assert client.post(
        "/api/conversations",
        json={"title": "越权", "project_id": bob_project["id"]},
        headers=_auth(alice),
    ).status_code == 404
    assert client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"project_id": bob_project["id"]},
        headers=_auth(alice),
    ).status_code == 404
    assert client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"pinned": True},
        headers=_auth(bob),
    ).status_code == 404
    assert client.patch(
        f"/api/documents/{document['id']}",
        json={"project_id": bob_project["id"]},
        headers=_auth(alice),
    ).status_code == 404


def test_document_project_patch_and_project_deletion_unassigns_resources(
    client, monkeypatch
):
    monkeypatch.setattr(
        documents, "get_document_task_dispatcher", lambda: FakeDocumentTaskDispatcher()
    )
    token = _register_and_login(client, "alice")
    project = _create_project(client, token).json()
    conversation = client.post(
        "/api/conversations",
        json={"title": "项目会话", "project_id": project["id"]},
        headers=_auth(token),
    ).json()
    document = _upload(client, token, "unlink.txt").json()

    assigned = client.patch(
        f"/api/documents/{document['id']}",
        json={"project_id": project["id"]},
        headers=_auth(token),
    )
    assert assigned.status_code == 200
    assert assigned.json()["project_id"] == project["id"]

    assert client.delete(f"/api/projects/{project['id']}", headers=_auth(token)).status_code == 204
    assert client.get(
        f"/api/conversations/{conversation['id']}", headers=_auth(token)
    ).json()["project_id"] is None
    assert client.get(
        f"/api/documents/{document['id']}", headers=_auth(token)
    ).json()["project_id"] is None


def test_project_activity_counts_sorting_and_document_upload(client, db, monkeypatch):
    monkeypatch.setattr(
        documents, "get_document_task_dispatcher", lambda: FakeDocumentTaskDispatcher()
    )
    token = _register_and_login(client, "alice")
    first = _create_project(client, token, name="first").json()
    second = _create_project(client, token, name="second").json()

    first_model = db.get(Project, first["id"])
    second_model = db.get(Project, second["id"])
    first_model.last_activity_at = first_model.created_at.replace(year=2020)
    second_model.last_activity_at = second_model.created_at.replace(year=2021)
    db.commit()
    assert [item["id"] for item in client.get("/api/projects", headers=_auth(token)).json()] == [
        second["id"],
        first["id"],
    ]

    pinned = client.patch(
        f"/api/projects/{first['id']}",
        json={"pinned": True},
        headers=_auth(token),
    )
    assert pinned.status_code == 200
    first_model = db.get(Project, first["id"])
    first_model.last_activity_at = first_model.created_at.replace(year=2020)
    db.commit()
    assert [item["id"] for item in client.get("/api/projects", headers=_auth(token)).json()] == [
        first["id"],
        second["id"],
    ]

    previous_activity = db.get(Project, first["id"]).last_activity_at
    conversation = client.post(
        "/api/conversations",
        json={"title": "project conversation", "project_id": first["id"]},
        headers=_auth(token),
    )
    assert conversation.status_code == 201
    after_conversation = client.get(
        f"/api/projects/{first['id']}", headers=_auth(token)
    ).json()
    assert after_conversation["last_activity_at"] != previous_activity.isoformat()
    assert after_conversation["conversation_count"] == 1

    previous_activity = after_conversation["last_activity_at"]
    document = _upload(client, token, "linked.txt", first["id"])
    assert document.status_code == 202
    assert document.json()["project_id"] == first["id"]
    after_document = client.get(
        f"/api/projects/{first['id']}", headers=_auth(token)
    ).json()
    assert after_document["last_activity_at"] != previous_activity
    assert after_document["document_count"] == 1

    previous_activity = after_document["last_activity_at"]
    updated = client.patch(
        f"/api/projects/{first['id']}",
        json={"instructions": "always use concise answers"},
        headers=_auth(token),
    )
    assert updated.status_code == 200
    assert updated.json()["last_activity_at"] != previous_activity


def test_conversation_rename_move_and_delete_touch_affected_projects(client, db):
    token = _register_and_login(client, "alice")
    first = _create_project(client, token, name="first").json()
    second = _create_project(client, token, name="second").json()
    conversation = client.post(
        "/api/conversations",
        json={"title": "original", "project_id": first["id"]},
        headers=_auth(token),
    ).json()
    old_activity = datetime(2020, 1, 1, 0, 0, 0)

    first_model = db.get(Project, first["id"])
    first_model.last_activity_at = old_activity
    db.commit()
    renamed = client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"title": "renamed"},
        headers=_auth(token),
    )
    assert renamed.status_code == 200
    db.expire_all()
    assert db.get(Project, first["id"]).last_activity_at > old_activity

    first_model = db.get(Project, first["id"])
    second_model = db.get(Project, second["id"])
    first_model.last_activity_at = old_activity
    second_model.last_activity_at = old_activity
    db.commit()
    moved = client.patch(
        f"/api/conversations/{conversation['id']}",
        json={"project_id": second["id"]},
        headers=_auth(token),
    )
    assert moved.status_code == 200
    db.expire_all()
    assert db.get(Project, first["id"]).last_activity_at > old_activity
    assert db.get(Project, second["id"]).last_activity_at > old_activity

    second_model = db.get(Project, second["id"])
    second_model.last_activity_at = old_activity
    db.commit()
    deleted = client.delete(
        f"/api/conversations/{conversation['id']}", headers=_auth(token)
    )
    assert deleted.status_code == 204
    db.expire_all()
    assert db.get(Project, second["id"]).last_activity_at > old_activity


def test_document_upload_rejects_another_users_project(client, monkeypatch):
    monkeypatch.setattr(
        documents, "get_document_task_dispatcher", lambda: FakeDocumentTaskDispatcher()
    )
    alice = _register_and_login(client, "alice")
    bob = _register_and_login(client, "bob")
    bob_project = _create_project(client, bob).json()

    assert _upload(client, alice, "private.txt", bob_project["id"]).status_code == 404
