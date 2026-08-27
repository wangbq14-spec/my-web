def _register(client, email="alice@example.com", username="alice"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": "secret123"},
    )


def test_register(client):
    resp = _register(client)

    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "alice@example.com"
    assert data["username"] == "alice"
    assert "id" in data
    assert "hashed_password" not in data


def test_register_duplicate_email(client):
    _register(client)
    resp = _register(client, email="alice@example.com", username="other")

    assert resp.status_code == 400


def test_login_success(client):
    _register(client)
    resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret123"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    _register(client)
    resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )

    assert resp.status_code == 401


def test_me_unauthorized(client):
    resp = client.get("/api/auth/me")

    assert resp.status_code == 401


def test_me_authorized(client):
    _register(client)
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    token = login_resp.json()["access_token"]

    resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"
