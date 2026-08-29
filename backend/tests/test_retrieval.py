import pytest

from app.rag import processing, retrieval
from app.rag.vector_store.local import LocalVectorStore


class FakeEmbeddingProvider:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.lower()
        if "alpha" in lowered:
            return [1.0, 0.0]
        if "beta" in lowered:
            return [0.0, 1.0]
        return [1.0, 1.0]


@pytest.fixture()
def fake_rag(monkeypatch):
    provider = FakeEmbeddingProvider()
    store = LocalVectorStore()
    monkeypatch.setattr(processing, "get_embedding_provider", lambda: provider)
    monkeypatch.setattr(processing, "get_vector_store", lambda: store)
    monkeypatch.setattr(retrieval, "get_embedding_provider", lambda: provider)
    monkeypatch.setattr(retrieval, "get_vector_store", lambda: store)
    return store


def _register_and_login(client, username: str) -> str:
    client.post(
        "/api/auth/register",
        json={
            "email": f"{username}@example.com",
            "username": username,
            "password": "secret123",
        },
    )
    return client.post(
        "/api/auth/login", json={"username": username, "password": "secret123"}
    ).json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _upload(client, token: str, filename: str, content: bytes):
    return client.post(
        "/api/documents",
        files={"file": (filename, content, "text/plain")},
        headers=_auth(token),
    )


def test_retrieval_returns_document_metadata_and_content(client, fake_rag):
    token = _register_and_login(client, "alice")
    created = _upload(client, token, "display-name.txt", b"alpha content").json()

    response = client.post(
        "/api/retrieval/search", json={"query": "alpha"}, headers=_auth(token)
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "document_id": created["id"],
            "filename": "display-name.txt",
            "chunk_index": 0,
            "content": "alpha content",
            "score": 1.0,
        }
    ]


def test_retrieval_top_k_limits_results(client, fake_rag):
    token = _register_and_login(client, "alice")
    _upload(client, token, "alpha.txt", b"alpha")
    _upload(client, token, "beta.txt", b"beta")

    response = client.post(
        "/api/retrieval/search",
        json={"query": "alpha", "top_k": 1},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["content"] == "alpha"


@pytest.mark.parametrize("payload", [{"query": ""}, {"query": "alpha", "top_k": 0}, {"query": "alpha", "top_k": 21}])
def test_retrieval_validates_query_and_top_k(client, fake_rag, payload):
    token = _register_and_login(client, "alice")

    response = client.post("/api/retrieval/search", json=payload, headers=_auth(token))

    assert response.status_code == 422


def test_retrieval_does_not_return_other_users_documents(client, fake_rag):
    alice = _register_and_login(client, "alice")
    bob = _register_and_login(client, "bob")
    _upload(client, bob, "bob.txt", b"alpha private")

    response = client.post(
        "/api/retrieval/search", json={"query": "alpha"}, headers=_auth(alice)
    )

    assert response.status_code == 200
    assert response.json() == []
