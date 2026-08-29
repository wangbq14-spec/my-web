from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.rag import retrieval
from app.rag.vector_store.base import ChunkVector
from app.rag.vector_store.db import DbVectorStore
from app.services.document import soft_delete_document


def _create_document(
    session,
    *,
    user_id: int,
    filename: str,
    status: str = "ready",
    active_generation: int = 1,
    deleted_at: datetime | None = None,
) -> Document:
    document = Document(
        user_id=user_id,
        filename=filename,
        original_filename=filename,
        content_type="text/plain",
        file_size=1,
        status=status,
        processing_generation=active_generation,
        active_generation=active_generation,
        deleted_at=deleted_at,
    )
    session.add(document)
    session.flush()
    return document


def _create_user(session, username: str) -> User:
    user = User(
        email=f"{username}@example.com",
        username=username,
        hashed_password="not-used-in-this-test",
    )
    session.add(user)
    session.flush()
    return user


def _new_session_factory(session):
    return sessionmaker(bind=session.get_bind(), autocommit=False, autoflush=False)


def _begin_processing(session, document: Document, generation: int) -> None:
    document.status = "processing"
    document.processing_generation = generation
    document.deleted_at = None
    session.commit()


def _publish_ready(session, document: Document, generation: int) -> None:
    document.status = "ready"
    document.active_generation = generation
    session.commit()


def test_db_store_is_visible_to_independent_instances_and_after_restart(db):
    user = _create_user(db, "alice")
    document = _create_document(db, user_id=user.id, filename="shared.txt")
    db.commit()

    writer = DbVectorStore(_new_session_factory(db))
    _begin_processing(db, document, 1)
    writer.upsert_chunks(
        user.id,
        document.id,
        1,
        [ChunkVector(chunk_index=0, content="shared durable chunk", embedding=[1.0, 0.0])],
    )
    _publish_ready(db, document, 1)

    reader = DbVectorStore(_new_session_factory(db))
    assert [match.content for match in reader.search(user.id, [1.0, 0.0], 5)] == [
        "shared durable chunk"
    ]


def test_db_store_isolates_users_and_replaces_a_generation(db):
    alice = _create_user(db, "alice")
    bob = _create_user(db, "bob")
    document = _create_document(db, user_id=alice.id, filename="private.txt")
    db.commit()
    store = DbVectorStore(_new_session_factory(db))

    _begin_processing(db, document, 1)
    store.upsert_chunks(
        alice.id,
        document.id,
        1,
        [ChunkVector(chunk_index=0, content="old", embedding=[0.0, 1.0])],
    )
    store.upsert_chunks(
        alice.id,
        document.id,
        1,
        [ChunkVector(chunk_index=0, content="replacement", embedding=[1.0, 0.0])],
    )
    _publish_ready(db, document, 1)

    assert [match.content for match in store.search(alice.id, [1.0, 0.0], 5)] == [
        "replacement"
    ]
    assert store.search(bob.id, [1.0, 0.0], 5) == []


def test_db_store_excludes_stale_generations_and_non_ready_documents(db):
    user = _create_user(db, "alice")
    ready = _create_document(db, user_id=user.id, filename="ready.txt", status="processing")
    not_ready = [
        _create_document(db, user_id=user.id, filename="processing.txt", status="processing"),
        _create_document(db, user_id=user.id, filename="queued.txt", status="processing"),
        _create_document(db, user_id=user.id, filename="failed.txt", status="processing"),
        _create_document(
            db, user_id=user.id, filename="deleted.txt", status="processing"
        ),
    ]
    db.commit()
    store = DbVectorStore(_new_session_factory(db))

    _begin_processing(db, ready, 1)
    store.upsert_chunks(
        user.id,
        ready.id,
        1,
        [ChunkVector(chunk_index=0, content="stale", embedding=[1.0, 0.0])],
    )
    _begin_processing(db, ready, 2)
    store.upsert_chunks(
        user.id,
        ready.id,
        2,
        [ChunkVector(chunk_index=0, content="current", embedding=[1.0, 0.0])],
    )
    for document in not_ready:
        _begin_processing(db, document, 1)
        store.upsert_chunks(
            user.id,
            document.id,
            1,
            [ChunkVector(chunk_index=0, content=document.filename, embedding=[1.0, 0.0])],
        )

    _publish_ready(db, ready, 2)
    not_ready[1].status = "queued"
    not_ready[2].status = "failed"
    not_ready[3].status = "deleted"
    not_ready[3].deleted_at = datetime.now()
    db.commit()

    assert [match.content for match in store.search(user.id, [1.0, 0.0], 10)] == [
        "current"
    ]


def test_db_store_sorts_by_cosine_honors_top_k_and_deletes_document(db):
    user = _create_user(db, "alice")
    document = _create_document(db, user_id=user.id, filename="scores.txt")
    db.commit()
    store = DbVectorStore(_new_session_factory(db))
    _begin_processing(db, document, 1)
    store.upsert_chunks(
        user.id,
        document.id,
        1,
        [
            ChunkVector(chunk_index=0, content="best", embedding=[1.0, 0.0]),
            ChunkVector(chunk_index=1, content="second", embedding=[0.8, 0.2]),
        ],
    )
    _publish_ready(db, document, 1)

    assert [match.content for match in store.search(user.id, [1.0, 0.0], 1)] == [
        "best"
    ]
    assert [match.content for match in store.search(user.id, [1.0, 0.0], 5)] == [
        "best",
        "second",
    ]

    store.delete_document(user.id, document.id)

    assert store.search(user.id, [1.0, 0.0], 5) == []


class _FakeEmbeddingProvider:
    def embed_query(self, text: str) -> list[float]:
        assert text == "find alpha"
        return [1.0, 0.0]


def test_retrieve_keeps_filename_content_and_score_contract_with_db_store(db, monkeypatch):
    user = _create_user(db, "alice")
    document = _create_document(db, user_id=user.id, filename="display-name.txt")
    db.commit()
    store = DbVectorStore(_new_session_factory(db))
    _begin_processing(db, document, 1)
    store.upsert_chunks(
        user.id,
        document.id,
        1,
        [ChunkVector(chunk_index=0, content="alpha content", embedding=[1.0, 0.0])],
    )
    _publish_ready(db, document, 1)
    monkeypatch.setattr(retrieval, "get_embedding_provider", _FakeEmbeddingProvider)
    monkeypatch.setattr(retrieval, "get_vector_store", lambda: store)

    result = retrieval.retrieve(db, user.id, "find alpha", top_k=5)

    assert result == [
        retrieval.RetrievedChunk(
            document_id=document.id,
            filename="display-name.txt",
            chunk_index=0,
            content="alpha content",
            score=1.0,
        )
    ]


def test_db_store_rejects_soft_deleted_document_without_writing_chunks(db):
    user = _create_user(db, "alice")
    document = _create_document(db, user_id=user.id, filename="deleted-before-upsert.txt")
    db.commit()
    _begin_processing(db, document, 1)
    assert soft_delete_document(db, document.id, user.id) is True
    db.commit()

    with pytest.raises(ValueError, match="not available"):
        DbVectorStore(_new_session_factory(db)).upsert_chunks(
            user.id,
            document.id,
            1,
            [ChunkVector(chunk_index=0, content="must not persist", embedding=[1.0, 0.0])],
        )

    assert db.query(DocumentChunk).filter_by(document_id=document.id).all() == []
