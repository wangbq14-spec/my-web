"""Queue dispatching and database-backed task scheduling for documents."""

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import lru_cache

import redis
from rq import Queue
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.user import utcnow_naive

logger = logging.getLogger(__name__)


class DocumentTaskDispatcher(ABC):
    @abstractmethod
    def enqueue(self, document_id: int) -> None:
        """Request asynchronous processing for one persisted document."""


class RQDocumentTaskDispatcher(DocumentTaskDispatcher):
    """RQ dispatcher whose Redis connection is created only on first enqueue."""

    def __init__(self) -> None:
        self._queue: Queue | None = None

    def _get_queue(self) -> Queue:
        if self._queue is None:
            connection = redis.Redis.from_url(settings.REDIS_URL)
            self._queue = Queue(settings.DOCUMENT_TASK_QUEUE, connection=connection)
        return self._queue

    def enqueue(self, document_id: int) -> None:
        self._get_queue().enqueue("app.worker.process_document_task", document_id)


class FakeDocumentTaskDispatcher(DocumentTaskDispatcher):
    """In-memory dispatcher used by tests without a Redis server."""

    def __init__(self) -> None:
        self.enqueued_ids: list[int] = []

    def enqueue(self, document_id: int) -> None:
        self.enqueued_ids.append(document_id)


_test_dispatcher: DocumentTaskDispatcher | None = None


@lru_cache
def get_document_task_dispatcher() -> DocumentTaskDispatcher:
    return _test_dispatcher or RQDocumentTaskDispatcher()


def set_document_task_dispatcher_for_test(
    dispatcher: DocumentTaskDispatcher | None,
) -> None:
    """Override the cached dispatcher for a test; pass None to restore RQ."""
    global _test_dispatcher
    _test_dispatcher = dispatcher
    get_document_task_dispatcher.cache_clear()


def _log_dispatch(
    *, document_id: int | None, result: str, error_code: str | None = None
) -> None:
    logger.info(
        json.dumps(
            {
                "event": "document_task_dispatch",
                "service": "document-dispatcher",
                "task_id": None,
                "document_id": document_id,
                "generation": None,
                "stage": "retry" if error_code else "claim",
                "duration_ms": 0,
                "retry_count": None,
                "attempt": None,
                "result": result,
                "error_code": error_code,
                "worker_id": "document-dispatcher",
            }
        )
    )


def document_task_dispatch_cooldown_until(now: datetime | None = None) -> datetime:
    """Return the earliest time a successful delivery may be submitted again."""
    current_time = now or utcnow_naive()
    return current_time + timedelta(
        seconds=settings.DOCUMENT_TASK_DISPATCH_INTERVAL_SECONDS * 6
    )


def mark_document_task_dispatched(
    session: Session, document_id: int, now: datetime | None = None
) -> bool:
    """Apply the delivery cooldown unless a worker has already claimed it."""
    result = session.execute(
        update(Document)
        .where(
            Document.id == document_id,
            Document.status == "queued",
            Document.deleted_at.is_(None),
        )
        .values(next_retry_at=document_task_dispatch_cooldown_until(now))
    )
    return result.rowcount == 1


def schedule_pending_documents(session_factory: Callable[[], Session]) -> int:
    """Recover expired leases and submit each eligible queued document once.

    ``next_retry_at`` is both the retry due time and a durable delivery
    cooldown.  Reserving that marker with a conditional update before the
    external enqueue closes the race between concurrent dispatcher scans.  If
    enqueue fails, the original due value is restored so a later scan retries.
    """
    session = session_factory()
    try:
        now: datetime = utcnow_naive()
        expired_document_ids = session.scalars(
            select(Document.id).where(
                Document.deleted_at.is_(None),
                Document.status == "processing",
                Document.processing_lease_expires_at < now,
            )
        ).all()

        # Reclaim each crashed worker only once.  A concurrent dispatcher can
        # win this update, but then this scanner must not treat it as recovered.
        for document_id in expired_document_ids:
            recovered = session.execute(
                update(Document)
                .where(
                    Document.id == document_id,
                    Document.status == "processing",
                    Document.processing_lease_expires_at < now,
                    Document.deleted_at.is_(None),
                )
                .values(status="queued", processing_token=None)
            )
            if recovered.rowcount == 1:
                _log_dispatch(document_id=document_id, result="recovered")

        queued_documents = session.execute(
            select(Document.id, Document.next_retry_at).where(
                Document.status == "queued",
                Document.deleted_at.is_(None),
                or_(Document.next_retry_at.is_(None), Document.next_retry_at <= now),
            )
        ).all()
        dispatcher = get_document_task_dispatcher()
        scheduled = 0
        cooldown_until = document_task_dispatch_cooldown_until(now)
        for document_id, previous_next_retry_at in queued_documents:
            # This conditional write is the dispatch reservation.  Only its
            # winner may call the external queue, which prevents duplicate
            # deliveries from overlapping dispatcher scans.
            reserved = session.execute(
                update(Document)
                .where(
                    Document.id == document_id,
                    Document.status == "queued",
                    Document.deleted_at.is_(None),
                    or_(
                        Document.next_retry_at.is_(None),
                        Document.next_retry_at <= now,
                    ),
                )
                .values(next_retry_at=cooldown_until)
            )
            if reserved.rowcount != 1:
                continue
            try:
                dispatcher.enqueue(document_id)
                scheduled += 1
                _log_dispatch(document_id=document_id, result="enqueued")
            except Exception:
                # Undo only our reservation.  A worker (or another transition)
                # may have changed the row while the external enqueue failed.
                session.execute(
                    update(Document)
                    .where(
                        Document.id == document_id,
                        Document.status == "queued",
                        Document.deleted_at.is_(None),
                        Document.next_retry_at == cooldown_until,
                    )
                    .values(next_retry_at=previous_next_retry_at)
                )
                _log_dispatch(
                    document_id=document_id,
                    result="enqueue_failed",
                    error_code="queue_unavailable",
                )
        session.commit()
        return scheduled
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
