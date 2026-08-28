def _register_and_login(client, username: str) -> str:
    client.post(
        "/api/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "secret123",
        },
    )
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_create_unauthorized(client):
    resp = client.post("/api/conversations", json={"title": "x"})

    assert resp.status_code == 401


def test_create_success(client):
    token = _register_and_login(client, "alice")

    resp = client.post(
        "/api/conversations",
        json={"title": "我的会话", "model": "gpt-x"},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "我的会话"
    assert data["model"] == "gpt-x"
    assert "id" in data
    assert "user_id" not in data


def test_create_ownership_from_jwt_not_client(client):
    token_a = _register_and_login(client, "alice")
    token_b = _register_and_login(client, "bob")

    client.post("/api/conversations", json={"title": "A's"}, headers=_auth(token_a))

    a_list = client.get("/api/conversations", headers=_auth(token_a)).json()
    assert [c["title"] for c in a_list] == ["A's"]

    b_list = client.get("/api/conversations", headers=_auth(token_b)).json()
    assert b_list == []


def test_list_only_own_conversations(client):
    token_a = _register_and_login(client, "alice")
    token_b = _register_and_login(client, "bob")

    client.post("/api/conversations", json={"title": "A1"}, headers=_auth(token_a))
    client.post("/api/conversations", json={"title": "A2"}, headers=_auth(token_a))
    client.post("/api/conversations", json={"title": "B1"}, headers=_auth(token_b))

    result = client.get("/api/conversations", headers=_auth(token_a)).json()

    assert [c["title"] for c in result] == ["A2", "A1"]


def test_get_own_conversation(client):
    token_a = _register_and_login(client, "alice")
    created = client.post(
        "/api/conversations", json={"title": "A1"}, headers=_auth(token_a)
    ).json()

    resp = client.get(f"/api/conversations/{created['id']}", headers=_auth(token_a))

    assert resp.status_code == 200
    assert resp.json()["title"] == "A1"


def test_get_other_users_conversation_returns_404(client):
    token_a = _register_and_login(client, "alice")
    token_b = _register_and_login(client, "bob")
    created_b = client.post(
        "/api/conversations", json={"title": "B1"}, headers=_auth(token_b)
    ).json()

    resp = client.get(f"/api/conversations/{created_b['id']}", headers=_auth(token_a))

    assert resp.status_code == 404


def test_get_nonexistent_conversation_returns_404(client):
    token_a = _register_and_login(client, "alice")

    resp = client.get("/api/conversations/999999", headers=_auth(token_a))

    assert resp.status_code == 404


def test_delete_own_conversation(client):
    token_a = _register_and_login(client, "alice")
    created = client.post(
        "/api/conversations", json={"title": "A1"}, headers=_auth(token_a)
    ).json()

    resp = client.delete(f"/api/conversations/{created['id']}", headers=_auth(token_a))

    assert resp.status_code == 204
    assert resp.content == b""


def test_delete_then_get_returns_404(client):
    token_a = _register_and_login(client, "alice")
    created = client.post(
        "/api/conversations", json={"title": "A1"}, headers=_auth(token_a)
    ).json()
    client.delete(f"/api/conversations/{created['id']}", headers=_auth(token_a))

    resp = client.get(f"/api/conversations/{created['id']}", headers=_auth(token_a))

    assert resp.status_code == 404


def test_delete_other_users_conversation_returns_404(client):
    token_a = _register_and_login(client, "alice")
    token_b = _register_and_login(client, "bob")
    created_b = client.post(
        "/api/conversations", json={"title": "B1"}, headers=_auth(token_b)
    ).json()

    resp = client.delete(f"/api/conversations/{created_b['id']}", headers=_auth(token_a))

    assert resp.status_code == 404


def test_list_unauthorized(client):
    resp = client.get("/api/conversations")

    assert resp.status_code == 401


def test_delete_unauthorized(client):
    resp = client.delete("/api/conversations/1")

    assert resp.status_code == 401


def test_create_with_user_id_field_422(client):
    token_a = _register_and_login(client, "alice")

    resp = client.post(
        "/api/conversations",
        json={"title": "x", "user_id": 1},
        headers=_auth(token_a),
    )

    assert resp.status_code == 422


def test_create_title_too_long_422(client):
    token_a = _register_and_login(client, "alice")

    resp = client.post(
        "/api/conversations",
        json={"title": "x" * 201},
        headers=_auth(token_a),
    )

    assert resp.status_code == 422


def test_list_order_updated_at_desc_id_desc(client):
    token_a = _register_and_login(client, "alice")
    for title in ["t1", "t2", "t3"]:
        client.post(
            "/api/conversations", json={"title": title}, headers=_auth(token_a)
        )

    result = client.get("/api/conversations", headers=_auth(token_a)).json()

    assert [c["title"] for c in result] == ["t3", "t2", "t1"]
