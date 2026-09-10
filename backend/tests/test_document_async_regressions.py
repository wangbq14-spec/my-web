from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from threading import Event, Thread

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.db.base import Base
from app.models.document import Document, DocumentChunk
from app.models.user import User, utcnow_naive
from app.rag.parsers.base import ParsedDocument
from app.rag.vector_store.base import ChunkVector
from app.rag.vector_store.db import DbVectorStore
from app.services.document import (
    claim_document,
    delete_document_chunks,
    mark_ready,
    soft_delete_document,
)
from app.services.document_backfill import mark_ready_documents_for_reindex
from app.services.document_tasks import (
    FakeDocumentTaskDispatcher,
    schedule_pending_documents,
    set_document_task_dispatcher_for_test,
)


class _EmbeddingProvider:
    def __init__(self, before_embed: Callable[[], None] | None = None) -> None:
        self._before_embed = before_embed

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._before_embed is not None:
            self._before_embed()
        return [[1.0, 0.0] for _ in texts]


def _document(db: Session, *, status: str = "queued") -> Document:
    user = User(
        email="async-regression@example.com",
        username="async-regression",
        hashed_password="not-used",
    )
    db.add(user)
    db.flush()
    document = Document(
        user_id=user.id,
        filename="async-regression.txt",
        original_filename="async-regression.txt",
        content_type="text/plain",
        file_size=5,
        status=status,
    )
    db.add(document)
    db.commit()
    return document


def _session_factory(db: Session):
    return sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)


def _configure_real_worker(
    monkeypatch,
    session_factory,
    *,
    provider: _EmbeddingProvider | None = None,
    vector_store=None,
) -> DbVectorStore:
    store = vector_store or DbVectorStore(session_factory)
    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(worker, "parse_document", lambda *_: ParsedDocument("alpha", {}))
    monkeypatch.setattr(worker.chunking, "chunk_text", lambda _: ["alpha"])
    monkeypatch.setattr(
        worker,
        "get_embedding_provider",
        lambda: provider or _EmbeddingProvider(),
    )
    monkeypatch.setattr(worker, "get_vector_store", lambda: store)
    return store


def _chunks(db: Session, document_id: int) -> list[DocumentChunk]:
    return list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.generation, DocumentChunk.chunk_index)
        )
    )


def test_backfill_reindexes_legacy_ready_documents_with_missing_embeddings(
    db, monkeypatch
):
    legacy = _document(db, status="ready")
    missing_chunks = Document(
        user_id=legacy.user_id,
        filename="missing-chunks.txt",
        original_filename="missing-chunks.txt",
        content_type="text/plain",
        file_size=5,
        status="ready",
    )
    healthy = Document(
        user_id=legacy.user_id,
        filename="healthy.txt",
        original_filename="healthy.txt",
        content_type="text/plain",
        file_size=5,
        status="ready",
    )
    db.add_all([missing_chunks, healthy])
    db.flush()
    db.add_all(
        [
            DocumentChunk(
                document_id=legacy.id,
                generation=0,
                chunk_index=0,
                content="legacy chunk",
                char_count=12,
                embedding=None,
            ),
            DocumentChunk(
                document_id=healthy.id,
                generation=0,
                chunk_index=0,
                content="healthy chunk",
                char_count=13,
                embedding="[1.0, 0.0]",
            ),
        ]
    )
    db.commit()

    assert mark_ready_documents_for_reindex(db) == 2
    db.commit()
    db.expire_all()
    assert db.get(Document, legacy.id).status == "queued"
    assert db.get(Document, missing_chunks.id).status == "queued"
    assert db.get(Document, healthy.id).status == "ready"

    store = _configure_real_worker(monkeypatch, _session_factory(db))
    worker.process_document_task(legacy.id)

    db.expire_all()
    ready = db.get(Document, legacy.id)
    assert ready.status == "ready"
    assert [(chunk.content, chunk.embedding) for chunk in _chunks(db, legacy.id)] == [
        ("alpha", "[1.0, 0.0]")
    ]
    assert [match.document_id for match in store.search(legacy.user_id, [1.0, 0.0], 1)] == [
        legacy.id
    ]


def test_delete_queued_document_is_not_rescheduled_and_cleans_chunks(db):
    document = _document(db)
    db.add(
        DocumentChunk(
            document_id=document.id,
            generation=0,
            chunk_index=0,
            content="queued residue",
            char_count=13,
            embedding="[1.0, 0.0]",
        )
    )
    db.commit()
    dispatcher = FakeDocumentTaskDispatcher()
    set_document_task_dispatcher_for_test(dispatcher)
    try:
        assert soft_delete_document(db, document.id, document.user_id) is True
        delete_document_chunks(db, document_id=document.id)
        db.commit()

        assert schedule_pending_documents(_session_factory(db)) == 0
    finally:
        set_document_task_dispatcher_for_test(None)

    db.expire_all()
    deleted = db.get(Document, document.id)
    assert deleted.status == "deleted"
    assert dispatcher.enqueued_ids == []
    assert _chunks(db, document.id) == []


def test_delete_after_worker_claim_fences_ready_and_removes_persisted_chunks(db):
    document = _document(db)
    assert claim_document(db, document.id, document.user_id, "claim-token", 60) is True
    db.commit()
    generation = db.get(Document, document.id).processing_generation

    DbVectorStore(_session_factory(db)).upsert_chunks(
        document.user_id,
        document.id,
        generation,
        [ChunkVector(0, "staging vector", [1.0, 0.0])],
    )

    assert soft_delete_document(db, document.id, document.user_id) is True
    delete_document_chunks(db, document_id=document.id)
    db.commit()

    assert mark_ready(db, document.id, document.user_id, "claim-token", generation) is False
    db.commit()
    db.expire_all()
    assert db.get(Document, document.id).status == "deleted"
    assert _chunks(db, document.id) == []


def test_upsert_fence_serializes_with_soft_delete_without_residual_chunks(
    tmp_path,
):
    """A delete started after the fence waits, then removes the committed chunks."""
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'upsert-delete-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    fenced = Event()
    release_upsert = Event()
    delete_started = Event()
    delete_finished = Event()
    errors: list[BaseException] = []

    def pause_after_fence(conn, cursor, statement, parameters, context, executemany):
        del conn, cursor, parameters, context, executemany
        if statement.startswith(
            "UPDATE documents SET processing_started_at=documents.processing_started_at"
        ):
            fenced.set()
            assert release_upsert.wait(timeout=5)

    event.listen(engine, "after_cursor_execute", pause_after_fence)
    try:
        with sessions() as control:
            document = _document(control)
            assert claim_document(
                control, document.id, document.user_id, "claim-token", 60
            ) is True
            control.commit()
            document_id, user_id = document.id, document.user_id
            generation = document.processing_generation

        def persist_chunks() -> None:
            try:
                DbVectorStore(sessions).upsert_chunks(
                    user_id,
                    document_id,
                    generation,
                    [ChunkVector(0, "racing vector", [1.0, 0.0])],
                )
            except BaseException as exc:
                errors.append(exc)

        def soft_delete() -> None:
            try:
                with sessions() as deleting:
                    delete_started.set()
                    assert soft_delete_document(deleting, document_id, user_id) is True
                    delete_document_chunks(deleting, document_id=document_id)
                    deleting.commit()
                    delete_finished.set()
            except BaseException as exc:
                errors.append(exc)

        upsert_thread = Thread(target=persist_chunks)
        upsert_thread.start()
        assert fenced.wait(timeout=5)

        delete_thread = Thread(target=soft_delete)
        delete_thread.start()
        assert delete_started.wait(timeout=5)
        assert not delete_finished.wait(timeout=0.1)

        release_upsert.set()
        upsert_thread.join(timeout=5)
        delete_thread.join(timeout=5)
        assert not upsert_thread.is_alive()
        assert not delete_thread.is_alive()
        assert errors == []

        with sessions() as control:
            document = control.get(Document, document_id)
            assert document.status == "deleted"
            assert document.deleted_at is not None
            assert _chunks(control, document_id) == []
    finally:
        release_upsert.set()
        event.remove(engine, "after_cursor_execute", pause_after_fence)
        engine.dispose()


def test_soft_delete_after_committed_upsert_removes_all_chunks(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'upsert-then-delete.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    try:
        with sessions() as control:
            document = _document(control)
            assert claim_document(
                control, document.id, document.user_id, "claim-token", 60
            ) is True
            control.add(
                DocumentChunk(
                    document_id=document.id,
                    generation=0,
                    chunk_index=0,
                    content="older vector",
                    char_count=12,
                    embedding="[1.0, 0.0]",
                )
            )
            control.commit()
            document_id, user_id = document.id, document.user_id
            generation = document.processing_generation

        DbVectorStore(sessions).upsert_chunks(
            user_id,
            document_id,
            generation,
            [ChunkVector(0, "current vector", [1.0, 0.0])],
        )

        with sessions() as deleting:
            assert soft_delete_document(deleting, document_id, user_id) is True
            delete_document_chunks(deleting, document_id=document_id)
            deleting.commit()

        with sessions() as control:
            document = control.get(Document, document_id)
            assert document.status == "deleted"
            assert _chunks(control, document_id) == []
    finally:
        engine.dispose()


def test_delete_between_vector_persist_and_ready_fences_worker(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'fence.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    persisted = Event()
    release_worker = Event()

    class PausingStore(DbVectorStore):
        def upsert_chunks(self, *args, **kwargs) -> None:
            super().upsert_chunks(*args, **kwargs)
            persisted.set()
            assert release_worker.wait(timeout=5)

    try:
        with sessions() as control:
            document = _document(control)
            document_id, user_id = document.id, document.user_id

        _configure_real_worker(monkeypatch, sessions, vector_store=PausingStore(sessions))
        thread = Thread(target=worker.process_document_task, args=(document_id,))
        thread.start()
        assert persisted.wait(timeout=5)

        with sessions() as control:
            assert soft_delete_document(control, document_id, user_id) is True
            delete_document_chunks(control, document_id=document_id)
            control.commit()

        release_worker.set()
        thread.join(timeout=5)
        assert not thread.is_alive()

        with sessions() as control:
            document = control.get(Document, document_id)
            assert document.status == "deleted"
            assert _chunks(control, document_id) == []
    finally:
        release_worker.set()
        engine.dispose()


def test_commit_failure_after_vector_persist_rolls_back_to_retryable_state(
    tmp_path, monkeypatch
):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'commit-failure.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    class FailingPublicationCommitSession:
        def __init__(self) -> None:
            self._session = sessions()
            self._commit_count = 0

        def __getattr__(self, name):
            return getattr(self._session, name)

        def commit(self) -> None:
            self._commit_count += 1
            if self._commit_count == 2:
                raise OperationalError("COMMIT", {}, RuntimeError("database unavailable"))
            self._session.commit()

        def close(self) -> None:
            self._session.close()

    try:
        with sessions() as control:
            document = _document(control)
            document_id = document.id

        _configure_real_worker(monkeypatch, FailingPublicationCommitSession)

        worker.process_document_task(document_id)

        with sessions() as control:
            document = control.get(Document, document_id)
            assert document.status in {"queued", "failed"}
            assert document.status != "processing"
            assert _chunks(control, document_id) == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("crash_stage", ["after_parse", "after_chunking", "after_upsert"])
def test_expired_crashed_worker_is_rescheduled_and_reclaimed_without_duplicate_chunks(
    db, monkeypatch, crash_stage
):
    document = _document(db)
    sessions = _session_factory(db)
    crash_once = {"raised": False}

    def crash() -> None:
        if not crash_once["raised"]:
            crash_once["raised"] = True
            raise SystemExit(f"simulated worker crash {crash_stage}")

    class CrashAfterUpsertStore(DbVectorStore):
        def upsert_chunks(self, *args, **kwargs) -> None:
            super().upsert_chunks(*args, **kwargs)
            if crash_stage == "after_upsert":
                crash()

    provider = _EmbeddingProvider(crash if crash_stage == "after_chunking" else None)
    _configure_real_worker(
        monkeypatch,
        sessions,
        provider=provider,
        vector_store=CrashAfterUpsertStore(sessions),
    )
    if crash_stage == "after_parse":
        monkeypatch.setattr(
            worker.chunking,
            "chunk_text",
            lambda _: (_ for _ in ()).throw(SystemExit("simulated worker crash after_parse")),
        )

    with pytest.raises(SystemExit):
        worker.process_document_task(document.id)

    db.expire_all()
    claimed = db.get(Document, document.id)
    assert claimed.status == "processing"
    claimed.processing_lease_expires_at = utcnow_naive() - timedelta(seconds=1)
    db.commit()
    dispatcher = FakeDocumentTaskDispatcher()
    set_document_task_dispatcher_for_test(dispatcher)
    try:
        assert schedule_pending_documents(sessions) == 1
    finally:
        set_document_task_dispatcher_for_test(None)
    assert dispatcher.enqueued_ids == [document.id]

    monkeypatch.setattr(worker.chunking, "chunk_text", lambda _: ["alpha"])
    monkeypatch.setattr(worker, "get_embedding_provider", lambda: _EmbeddingProvider())

    worker.process_document_task(document.id)

    db.expire_all()
    ready = db.get(Document, document.id)
    assert ready.status == "ready"
    chunks = _chunks(db, document.id)
    assert [(chunk.generation, chunk.chunk_index, chunk.content) for chunk in chunks] == [
        (ready.active_generation, 0, "alpha")
    ]
