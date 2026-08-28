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


def _create_conversation(client, token: str, title: str = "c1") -> int:
    resp = client.post(
        "/api/conversations", json={"title": title}, headers=_auth(token)
    )
    return resp.json()["id"]


def test_post_message_unauthorized(client):
    resp = client.post("/api/conversations/1/messages", json={"content": "hi"})

    assert resp.status_code == 401


def test_post_message_success(client):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "你好"},
        headers=_auth(token),
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["content"] == "你好"
    assert data["role"] == "user"
    assert data["conversation_id"] == conv_id
    assert "id" in data


def test_post_message_on_other_users_conversation_returns_404(client):
    token_a = _register_and_login(client, "alice")
    token_b = _register_and_login(client, "bob")
    conv_b = _create_conversation(client, token_b)

    resp = client.post(
        f"/api/conversations/{conv_b}/messages",
        json={"content": "hi"},
        headers=_auth(token_a),
    )

    assert resp.status_code == 404


def test_get_own_messages_200(client):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "m1"},
        headers=_auth(token),
    )

    resp = client.get(f"/api/conversations/{conv_id}/messages", headers=_auth(token))

    assert resp.status_code == 200
    assert [m["content"] for m in resp.json()] == ["m1"]


def test_get_other_users_messages_404(client):
    token_a = _register_and_login(client, "alice")
    token_b = _register_and_login(client, "bob")
    conv_b = _create_conversation(client, token_b)

    resp = client.get(f"/api/conversations/{conv_b}/messages", headers=_auth(token_a))

    assert resp.status_code == 404


def test_get_nonexistent_conversation_messages_404(client):
    token = _register_and_login(client, "alice")

    resp = client.get("/api/conversations/999999/messages", headers=_auth(token))

    assert resp.status_code == 404


def test_post_message_role_extra_422(client):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "hi", "role": "assistant"},
        headers=_auth(token),
    )

    assert resp.status_code == 422


def test_post_message_conversation_id_extra_422(client):
    token = _register_and_login(client, "alice")
    conv_id = _create_conversation(client, token)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "hi", "conversation_id": conv_id},
        headers=_auth(token),
    )

    assert resp.status_code == 422
