import pytest
from sqlalchemy import select

from app.models.document import Document, DocumentChunk
from app.rag import processing, retrieval
from app.rag.embeddings.base import EmbeddingError
from app.rag.parsers.base import ParserError
from app.rag.vector_store.local import LocalVectorStore


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.text_error: Exception | None = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.text_error is not None:
            raise self.text_error
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
    return provider, store


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


def test_processing_success_sets_ready_persists_chunks_and_indexes(client, db, fake_rag):
    token = _register_and_login(client, "alice")

    response = _upload(client, token, "notes.txt", b"alpha content")

    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "ready"
    chunks = db.scalars(
        select(DocumentChunk).where(DocumentChunk.document_id == created["id"])
    ).all()
    assert [(chunk.chunk_index, chunk.content, chunk.char_count) for chunk in chunks] == [
        (0, "alpha content", len("alpha content"))
    ]
    _, store = fake_rag
    assert store.search(1, [1.0, 0.0], 5)[0].content == "alpha content"


def test_parser_failure_marks_document_failed_without_chunks_or_vectors(
    client, db, fake_rag, monkeypatch
):
    token = _register_and_login(client, "alice")
    monkeypatch.setattr(processing, "parse_document", lambda *_: (_ for _ in ()).throw(ParserError("/secret/path")))

    response = _upload(client, token, "broken.txt", b"alpha")

    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "failed"
    assert created["error_message"] == "文档解析失败"
    assert "/secret/path" not in created["error_message"]
    assert db.scalars(select(DocumentChunk)).all() == []
    _, store = fake_rag
    assert store.search(1, [1.0, 0.0], 5) == []


def test_embedding_failure_marks_failed_and_cleans_up(client, db, fake_rag):
    token = _register_and_login(client, "alice")
    provider, store = fake_rag
    provider.text_error = EmbeddingError("api-key=not-for-client")

    response = _upload(client, token, "broken.txt", b"alpha")

    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert response.json()["error_message"] == "Embedding 服务不可用"
    assert "api-key" not in response.json()["error_message"]
    assert db.scalars(select(DocumentChunk)).all() == []
    assert store.search(1, [1.0, 0.0], 5) == []


def test_vector_upsert_failure_marks_failed_and_cleans_up(client, db, fake_rag, monkeypatch):
    token = _register_and_login(client, "alice")
    _, store = fake_rag

    def partially_write_then_fail(user_id, document_id, chunks):
        store._documents[(user_id, document_id)] = list(chunks)
        raise RuntimeError("vector backend failed")

    monkeypatch.setattr(store, "upsert_chunks", partially_write_then_fail)

    response = _upload(client, token, "broken.txt", b"alpha")

    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert response.json()["error_message"] == "文档处理失败"
    assert db.scalars(select(DocumentChunk)).all() == []
    assert store.search(1, [1.0, 0.0], 5) == []


def test_upload_search_delete_removes_file_chunks_and_vectors(client, db, fake_rag):
    token = _register_and_login(client, "alice")
    uploaded = _upload(client, token, "notes.txt", b"alpha content")
    created = uploaded.json()
    from app.rag.storage import resolve_upload_path

    stored_path = resolve_upload_path(created["filename"])
    search = client.post(
        "/api/retrieval/search", json={"query": "alpha"}, headers=_auth(token)
    )
    assert uploaded.status_code == 201
    assert created["status"] == "ready"
    assert search.status_code == 200
    assert search.json()[0]["content"] == "alpha content"

    deleted = client.delete(f"/api/documents/{created['id']}", headers=_auth(token))

    assert deleted.status_code == 204
    assert not stored_path.exists()
    assert db.get(Document, created["id"]) is None
    assert db.scalars(select(DocumentChunk)).all() == []
    assert client.post(
        "/api/retrieval/search", json={"query": "alpha"}, headers=_auth(token)
    ).json() == []
