"""RQ worker and MySQL-backed dispatcher for asynchronous document processing."""

import argparse
import json
import logging
import os
import socket
import threading
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import redis
from rq import Queue, Worker, get_current_job
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.document import Document
from app.rag import chunking, storage
from app.rag.embeddings.base import EmbeddingError
from app.rag.embeddings.factory import get_embedding_provider
from app.rag.parsers import parse_document
from app.rag.parsers.base import ParserError
from app.rag.vector_store.base import ChunkVector
from app.rag.vector_store.db import DocumentProcessingCancelled
from app.rag.vector_store.factory import get_vector_store
from app.services.document import claim_document, mark_failed, mark_ready, reclaim_expired
from app.services.document_backfill import mark_ready_documents_for_reindex
from app.services.document_tasks import schedule_pending_documents

logger = logging.getLogger(__name__)
_WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
_DOCUMENT_BACKFILL_INTERVAL_MULTIPLIER = 12


def _task_id() -> str | None:
    job = get_current_job()
    return job.id if job is not None else None


def _log_task(
    *,
    document_id: int,
    generation: int | None,
    stage: str,
    duration_ms: int,
    retry_count: int | None,
    result: str,
    error_code: str | None = None,
) -> None:
    """Emit redacted, machine-readable worker events only."""
    logger.info(
        json.dumps(
            {
                "event": "document_task",
                "service": "document-worker",
                "task_id": _task_id(),
                "document_id": document_id,
                "generation": generation,
                "stage": stage,
                "duration_ms": duration_ms,
                "retry_count": retry_count,
                "attempt": None if retry_count is None else retry_count + 1,
                "result": result,
                "error_code": error_code,
                "worker_id": _WORKER_ID,
            },
            ensure_ascii=False,
        )
    )


def _record_failure(
    session: Session,
    *,
    document_id: int,
    user_id: int,
    token: str,
    generation: int,
    retry_count: int,
    error_code: str,
    retryable: bool,
    started_at: float,
) -> None:
    outcome = mark_failed(
        session,
        document_id,
        user_id,
        error_code=error_code,
        error_message="Document processing could not be completed.",
        retryable=retryable,
        retry_count_cap=settings.DOCUMENT_TASK_MAX_RETRIES,
        base_seconds=settings.DOCUMENT_TASK_RETRY_BASE_SECONDS,
        max_seconds=settings.DOCUMENT_TASK_RETRY_MAX_SECONDS,
        token=token,
        generation=generation,
    )
    if outcome == "cancelled":
        session.rollback()
        _log_task(
            document_id=document_id,
            generation=generation,
            stage="cancelled",
            duration_ms=int((perf_counter() - started_at) * 1000),
            retry_count=retry_count,
            result="cancelled",
            error_code=error_code,
        )
        return

    session.commit()
    _log_task(
        document_id=document_id,
        generation=generation,
        stage="retry" if outcome == "queued" else "failed",
        duration_ms=int((perf_counter() - started_at) * 1000),
        retry_count=retry_count,
        result=outcome,
        error_code=error_code,
    )


def process_document_task(document_id: int) -> None:
    """Claim, process, and fence-publish a single document task.

    The RQ payload contains only ``document_id``. The worker obtains all
    ownership and file metadata from its own database session.
    """
    started_at = perf_counter()
    session = SessionLocal()
    generation: int | None = None
    retry_count: int | None = None
    try:
        document = session.get(Document, document_id)
        if document is None:
            _log_task(
                document_id=document_id,
                generation=None,
                stage="claim",
                duration_ms=int((perf_counter() - started_at) * 1000),
                retry_count=None,
                result="noop",
            )
            return

        user_id = document.user_id
        token = uuid4().hex
        claimed = claim_document(
            session,
            document_id,
            user_id,
            token,
            settings.DOCUMENT_TASK_LEASE_SECONDS,
        )
        if not claimed:
            claimed = reclaim_expired(
                session,
                document_id,
                user_id,
                token,
                settings.DOCUMENT_TASK_LEASE_SECONDS,
            )
        if not claimed:
            session.rollback()
            _log_task(
                document_id=document_id,
                generation=None,
                stage="claim",
                duration_ms=int((perf_counter() - started_at) * 1000),
                retry_count=None,
                result="noop",
            )
            return

        # Persist the lease before a separate DbVectorStore session writes
        # staging chunks. It also lets another worker reclaim an expired lease.
        session.commit()
        document = session.get(Document, document_id)
        if document is None:
            _log_task(
                document_id=document_id,
                generation=None,
                stage="cancelled",
                duration_ms=int((perf_counter() - started_at) * 1000),
                retry_count=None,
                result="cancelled",
            )
            return

        generation = document.processing_generation
        retry_count = document.retry_count
        _log_task(
            document_id=document_id,
            generation=generation,
            stage="claim",
            duration_ms=int((perf_counter() - started_at) * 1000),
            retry_count=retry_count,
            result="claimed",
        )

        try:
            path = storage.resolve_upload_path(document.filename)
            parsed = parse_document(path, Path(document.filename).suffix.lower())
            _log_task(
                document_id=document_id,
                generation=generation,
                stage="parse",
                duration_ms=int((perf_counter() - started_at) * 1000),
                retry_count=retry_count,
                result="success",
            )
            chunks = chunking.chunk_text(parsed.text)
            if not chunks:
                raise ParserError("Document has no usable content")
            _log_task(
                document_id=document_id,
                generation=generation,
                stage="chunk",
                duration_ms=int((perf_counter() - started_at) * 1000),
                retry_count=retry_count,
                result="success",
            )
            embeddings = get_embedding_provider().embed_texts(chunks)
            if len(embeddings) != len(chunks):
                raise EmbeddingError("Embedding count does not match chunks")
            _log_task(
                document_id=document_id,
                generation=generation,
                stage="embed",
                duration_ms=int((perf_counter() - started_at) * 1000),
                retry_count=retry_count,
                result="success",
            )
            get_vector_store().upsert_chunks(
                user_id,
                document_id,
                generation,
                [
                    ChunkVector(index, content, embedding)
                    for index, (content, embedding) in enumerate(
                        zip(chunks, embeddings, strict=True)
                    )
                ],
            )
            _log_task(
                document_id=document_id,
                generation=generation,
                stage="persist",
                duration_ms=int((perf_counter() - started_at) * 1000),
                retry_count=retry_count,
                result="success",
            )
        except DocumentProcessingCancelled:
            session.rollback()
            _log_task(
                document_id=document_id,
                generation=generation,
                stage="cancelled",
                duration_ms=int((perf_counter() - started_at) * 1000),
                retry_count=retry_count,
                result="cancelled",
            )
            return
        except ParserError:
            _record_failure(
                session,
                document_id=document_id,
                user_id=user_id,
                token=token,
                generation=generation,
                retry_count=retry_count,
                error_code="parse_error",
                retryable=False,
                started_at=started_at,
            )
            return
        except EmbeddingError:
            _record_failure(
                session,
                document_id=document_id,
                user_id=user_id,
                token=token,
                generation=generation,
                retry_count=retry_count,
                error_code="embedding_error",
                retryable=True,
                started_at=started_at,
            )
            return
        except Exception:
            _record_failure(
                session,
                document_id=document_id,
                user_id=user_id,
                token=token,
                generation=generation,
                retry_count=retry_count,
                error_code="processing_error",
                retryable=True,
                started_at=started_at,
            )
            return

        try:
            if mark_ready(session, document_id, user_id, token, generation):
                session.commit()
                _log_task(
                    document_id=document_id,
                    generation=generation,
                    stage="commit",
                    duration_ms=int((perf_counter() - started_at) * 1000),
                    retry_count=retry_count,
                    result="success",
                )
                return

            session.rollback()
            _log_task(
                document_id=document_id,
                generation=generation,
                stage="cancelled",
                duration_ms=int((perf_counter() - started_at) * 1000),
                retry_count=retry_count,
                result="cancelled",
            )
        except Exception:
            # The vectors were already persisted in their own transaction. Do not
            # leave the document permanently processing if publishing fails.
            session.rollback()
            try:
                _record_failure(
                    session,
                    document_id=document_id,
                    user_id=user_id,
                    token=token,
                    generation=generation,
                    retry_count=retry_count,
                    error_code="commit_failure",
                    retryable=True,
                    started_at=started_at,
                )
            except Exception:
                # The compensation itself could not be persisted. Its existing
                # lease remains in place and the dispatcher can reclaim it later.
                session.rollback()
                _log_task(
                    document_id=document_id,
                    generation=generation,
                    stage="commit",
                    duration_ms=int((perf_counter() - started_at) * 1000),
                    retry_count=retry_count,
                    result="error",
                    error_code="commit_failure",
                )
    finally:
        session.close()


def backfill_ready_documents() -> int:
    """Run the durable-embedding recovery once and commit its transition."""
    session = SessionLocal()
    try:
        requeued = mark_ready_documents_for_reindex(session)
        session.commit()
        return requeued
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _dispatcher_loop(stop_event: threading.Event) -> None:
    backfill_interval = (
        settings.DOCUMENT_TASK_DISPATCH_INTERVAL_SECONDS
        * _DOCUMENT_BACKFILL_INTERVAL_MULTIPLIER
    )
    next_backfill_at = 0.0
    while not stop_event.is_set():
        now = perf_counter()
        if now >= next_backfill_at:
            try:
                requeued = backfill_ready_documents()
                if requeued:
                    logger.info(
                        json.dumps(
                            {
                                "event": "document_embedding_backfill",
                                "service": "document-dispatcher",
                                "result": "requeued",
                                "document_count": requeued,
                                "worker_id": _WORKER_ID,
                            }
                        )
                    )
            except Exception:
                logger.exception("Document embedding backfill scan failed")
            next_backfill_at = now + backfill_interval
        try:
            schedule_pending_documents(SessionLocal)
        except Exception:
            logger.info(
                json.dumps(
                    {
                        "event": "document_task_dispatch",
                        "service": "document-dispatcher",
                        "task_id": None,
                        "document_id": None,
                        "generation": None,
                        "stage": "retry",
                        "duration_ms": 0,
                        "retry_count": None,
                        "attempt": None,
                        "result": "scan_failed",
                        "error_code": "scheduler_error",
                        "worker_id": _WORKER_ID,
                    }
                )
            )
        stop_event.wait(settings.DOCUMENT_TASK_DISPATCH_INTERVAL_SECONDS)


class _DocumentWorker(Worker):
    """Propagate RQ's warm shutdown signal to the dispatcher companion."""

    def __init__(self, *args, dispatcher_stop_event: threading.Event, **kwargs) -> None:
        self._dispatcher_stop_event = dispatcher_stop_event
        super().__init__(*args, **kwargs)

    def request_stop(self, signum, frame) -> None:
        self._dispatcher_stop_event.set()
        super().request_stop(signum, frame)


def main() -> None:
    """Run the RQ worker and a companion MySQL dispatcher loop."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="queue ready documents that need durable embedding regeneration",
    )
    args = parser.parse_args()
    if args.backfill:
        logger.info(
            "Queued %s ready document(s) for embedding regeneration.",
            backfill_ready_documents(),
        )
        return

    stop_event = threading.Event()
    connection = redis.Redis.from_url(settings.REDIS_URL)
    queue = Queue(settings.DOCUMENT_TASK_QUEUE, connection=connection)
    worker = _DocumentWorker(
        queues=[queue], connection=connection, dispatcher_stop_event=stop_event
    )
    dispatcher = threading.Thread(
        target=_dispatcher_loop, args=(stop_event,), name="document-dispatcher", daemon=True
    )

    dispatcher.start()
    try:
        worker.work()
    finally:
        stop_event.set()
        dispatcher.join(timeout=settings.DOCUMENT_TASK_DISPATCH_INTERVAL_SECONDS + 1)


if __name__ == "__main__":
    main()
