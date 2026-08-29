from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.document import Document, DocumentChunk
from app.models.user import User, utcnow_naive
from app.rag.embeddings.base import EmbeddingTimeoutError
from app.rag.parsers.base import ParsedDocument, ParserError
from app.rag.vector_store.base import ChunkVector
from app.services.document_tasks import (
    FakeDocumentTaskDispatcher,
    RQDocumentTaskDispatcher,
    document_task_dispatch_cooldown_until,
    get_document_task_dispatcher,
    schedule_pending_documents,
    set_document_task_dispatcher_for_test,
)
from app.services.document import reset_for_manual_retry
from app import worker


def _create_user_and_document(db, *, status: str = "queued") -> Document:
    user = User(
        email="worker@example.com",
        username="worker-user",
        hashed_password="not-used",
    )
    db.add(user)
    db.flush()
    document = Document(
        user_id=user.id,
        filename="worker.txt",
        original_filename="worker.txt",
        content_type="text/plain",
        file_size=10,
        status=status,
    )
    db.add(document)
    db.commit()
    return document


class _FakeVectorStore:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int, list[ChunkVector]]] = []

    def upsert_chunks(self, user_id, document_id, generation, chunks) -> None:
        self.calls.append((user_id, document_id, generation, chunks))


class _FakeEmbeddingProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.error is not None:
            raise self.error
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture()
def fake_dispatcher():
    dispatcher = FakeDocumentTaskDispatcher()
    set_document_task_dispatcher_for_test(dispatcher)
    try:
        yield dispatcher
    finally:
        set_document_task_dispatcher_for_test(None)


@pytest.fixture()
def worker_success_dependencies(monkeypatch):
    store = _FakeVectorStore()
    monkeypatch.setattr(worker, "parse_document", lambda *_: ParsedDocument("alpha", {}))
    monkeypatch.setattr(worker.chunking, "chunk_text", lambda _: ["alpha"])
    monkeypatch.setattr(worker, "get_embedding_provider", lambda: _FakeEmbeddingProvider())
    monkeypatch.setattr(worker, "get_vector_store", lambda: store)
    return store


def test_fake_dispatcher_can_be_injected(fake_dispatcher):
    assert get_document_task_dispatcher() is fake_dispatcher
    get_document_task_dispatcher().enqueue(42)
    assert fake_dispatcher.enqueued_ids == [42]


def test_rq_dispatcher_payload_contains_only_document_id(monkeypatch):
    calls: list[tuple[object, ...]] = []

    class RecordingQueue:
        def __init__(self, _name, connection):
            assert connection == "redis-connection"

        def enqueue(self, *args):
            calls.append(args)

    monkeypatch.setattr(
        "app.services.document_tasks.redis.Redis.from_url",
        lambda _url: "redis-connection",
    )
    monkeypatch.setattr("app.services.document_tasks.Queue", RecordingQueue)

    RQDocumentTaskDispatcher().enqueue(123)

    assert calls == [("app.worker.process_document_task", 123)]


def test_process_document_task_claims_processes_persists_and_marks_ready(
    db, monkeypatch, worker_success_dependencies
):
    document = _create_user_and_document(db)
    monkeypatch.setattr(worker, "SessionLocal", lambda: sessionmaker(bind=db.get_bind())())

    worker.process_document_task(document.id)

    db.expire_all()
    processed = db.get(Document, document.id)
    assert processed.status == "ready"
    assert processed.processing_generation == 1
    assert processed.active_generation == 1
    assert len(worker_success_dependencies.calls) == 1
    _, document_id, generation, chunks = worker_success_dependencies.calls[0]
    assert document_id == document.id
    assert generation == 1
    assert chunks[0].chunk_index == 0


def test_process_document_task_duplicate_delivery_is_a_noop(
    db, monkeypatch, worker_success_dependencies
):
    document = _create_user_and_document(db)
    monkeypatch.setattr(worker, "SessionLocal", lambda: sessionmaker(bind=db.get_bind())())

    worker.process_document_task(document.id)
    worker.process_document_task(document.id)

    assert len(worker_success_dependencies.calls) == 1


def test_embedding_timeout_requeues_with_future_retry_at(db, monkeypatch):
    document = _create_user_and_document(db)
    monkeypatch.setattr(worker, "SessionLocal", lambda: sessionmaker(bind=db.get_bind())())
    monkeypatch.setattr(worker, "parse_document", lambda *_: ParsedDocument("alpha", {}))
    monkeypatch.setattr(worker.chunking, "chunk_text", lambda _: ["alpha"])
    monkeypatch.setattr(
        worker,
        "get_embedding_provider",
        lambda: _FakeEmbeddingProvider(EmbeddingTimeoutError("timeout")),
    )
    before = utcnow_naive()

    worker.process_document_task(document.id)

    db.expire_all()
    failed = db.get(Document, document.id)
    assert failed.status == "queued"
    assert failed.retry_count == 1
    assert failed.next_retry_at is not None
    assert failed.next_retry_at >= before


def test_parser_error_fails_permanently_and_removes_all_chunks(db, monkeypatch):
    document = _create_user_and_document(db)
    db.add(
        DocumentChunk(
            document_id=document.id,
            generation=0,
            chunk_index=0,
            content="stale",
            char_count=5,
        )
    )
    db.commit()
    monkeypatch.setattr(worker, "SessionLocal", lambda: sessionmaker(bind=db.get_bind())())
    monkeypatch.setattr(
        worker,
        "parse_document",
        lambda *_: (_ for _ in ()).throw(ParserError("invalid document")),
    )

    worker.process_document_task(document.id)

    db.expire_all()
    assert db.get(Document, document.id).status == "failed"
    assert db.query(DocumentChunk).filter_by(document_id=document.id).all() == []


def test_schedule_pending_documents_enqueues_due_retry_once(db, fake_dispatcher):
    due = _create_user_and_document(db)
    due.next_retry_at = utcnow_naive() - timedelta(seconds=1)
    future = Document(
        user_id=due.user_id,
        filename="future.txt",
        original_filename="future.txt",
        content_type="text/plain",
        file_size=1,
        status="queued",
        next_retry_at=utcnow_naive() + timedelta(minutes=1),
    )
    deleted = Document(
        user_id=due.user_id,
        filename="deleted.txt",
        original_filename="deleted.txt",
        content_type="text/plain",
        file_size=1,
        status="queued",
        deleted_at=utcnow_naive(),
    )
    db.add_all([future, deleted])
    db.commit()

    session_factory = lambda: sessionmaker(bind=db.get_bind())()
    counts = [schedule_pending_documents(session_factory) for _ in range(5)]

    assert counts == [1, 0, 0, 0, 0]
    assert fake_dispatcher.enqueued_ids == [due.id]
    db.expire_all()
    assert db.get(Document, due.id).next_retry_at is not None
    assert db.get(Document, due.id).next_retry_at > utcnow_naive()


def test_schedule_pending_documents_recovers_expired_processing_once(
    db, fake_dispatcher
):
    document = _create_user_and_document(db, status="processing")
    document.processing_token = "crashed-worker"
    document.processing_generation = 3
    document.processing_lease_expires_at = utcnow_naive() - timedelta(seconds=1)
    db.commit()

    session_factory = lambda: sessionmaker(bind=db.get_bind())()
    assert [schedule_pending_documents(session_factory) for _ in range(2)] == [1, 0]
    assert fake_dispatcher.enqueued_ids == [document.id]

    db.expire_all()
    recovered = db.get(Document, document.id)
    assert recovered.status == "queued"
    assert recovered.processing_token is None
    assert recovered.processing_generation == 3
    assert recovered.next_retry_at is not None
    assert recovered.next_retry_at > utcnow_naive()


def test_schedule_enqueue_failure_leaves_document_queued(db):
    document = _create_user_and_document(db)
    document.next_retry_at = utcnow_naive() - timedelta(seconds=1)
    db.commit()

    class FailingDispatcher(FakeDocumentTaskDispatcher):
        def enqueue(self, document_id: int) -> None:
            raise ConnectionError(f"cannot enqueue {document_id}")

    set_document_task_dispatcher_for_test(FailingDispatcher())
    try:
        assert schedule_pending_documents(lambda: sessionmaker(bind=db.get_bind())()) == 0
    finally:
        set_document_task_dispatcher_for_test(None)

    db.expire_all()
    assert db.get(Document, document.id).status == "queued"


def test_schedule_retries_manual_retry_after_enqueue_failure_for_started_document(db):
    document = _create_user_and_document(db, status="failed")
    document.processing_generation = 2
    document.retry_count = 3
    db.commit()
    assert reset_for_manual_retry(db, document.id, document.user_id) is True
    db.commit()

    class FailingDispatcher(FakeDocumentTaskDispatcher):
        def enqueue(self, document_id: int) -> None:
            raise ConnectionError(f"cannot enqueue {document_id}")

    session_factory = lambda: sessionmaker(bind=db.get_bind())()
    set_document_task_dispatcher_for_test(FailingDispatcher())
    try:
        assert schedule_pending_documents(session_factory) == 0
    finally:
        set_document_task_dispatcher_for_test(None)

    db.expire_all()
    retry = db.get(Document, document.id)
    assert retry.status == "queued"
    assert retry.processing_generation == 2
    assert retry.next_retry_at is None
    retry.next_retry_at = utcnow_naive() - timedelta(seconds=1)
    db.commit()

    dispatcher = FakeDocumentTaskDispatcher()
    set_document_task_dispatcher_for_test(dispatcher)
    try:
        assert schedule_pending_documents(session_factory) == 1
    finally:
        set_document_task_dispatcher_for_test(None)
    assert dispatcher.enqueued_ids == [document.id]


def test_concurrent_dispatcher_scans_reserve_a_queued_document_once(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'dispatcher-concurrency.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    dispatcher = FakeDocumentTaskDispatcher()
    barrier = Barrier(2)
    try:
        with sessions() as session:
            user = User(
                email="dispatcher@example.com",
                username="dispatcher-user",
                hashed_password="not-used",
            )
            session.add(user)
            session.flush()
            document = Document(
                user_id=user.id,
                filename="dispatcher.txt",
                original_filename="dispatcher.txt",
                content_type="text/plain",
                file_size=1,
                status="queued",
            )
            session.add(document)
            session.commit()
            document_id = document.id

        set_document_task_dispatcher_for_test(dispatcher)

        def scan() -> int:
            barrier.wait(timeout=5)
            return schedule_pending_documents(sessions)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: scan(), range(2)))

        assert sorted(results) == [0, 1]
        assert dispatcher.enqueued_ids == [document_id]
        with sessions() as session:
            document = session.get(Document, document_id)
            assert document.next_retry_at is not None
            assert document.next_retry_at <= document_task_dispatch_cooldown_until()
    finally:
        set_document_task_dispatcher_for_test(None)
        engine.dispose()


def test_worker_closes_its_own_session(db, monkeypatch, worker_success_dependencies):
    document = _create_user_and_document(db)
    closed: list[bool] = []

    class TrackingSession:
        def __init__(self) -> None:
            self._session: Session = sessionmaker(bind=db.get_bind())()

        def __getattr__(self, name):
            return getattr(self._session, name)

        def close(self) -> None:
            self._session.close()
            closed.append(True)

    monkeypatch.setattr(worker, "SessionLocal", TrackingSession)

    worker.process_document_task(document.id)

    assert closed == [True]
