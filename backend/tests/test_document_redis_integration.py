import os
from uuid import uuid4

import pytest
import redis
from rq import Queue, SimpleWorker

from app import worker
from app.core.config import settings
from app.services.document_tasks import RQDocumentTaskDispatcher


def _redis_connection_or_skip():
    url = os.getenv("REDIS_URL", "")
    required = os.getenv("REQUIRE_REDIS_INTEGRATION") == "1"
    if not url:
        message = "REDIS_URL is required for the Redis integration test"
        if required:
            pytest.fail(message)
        pytest.skip(message)
    connection = redis.Redis.from_url(url)
    try:
        connection.ping()
    except redis.RedisError as exc:
        message = f"Redis integration is unavailable: {exc}"
        if required:
            pytest.fail(message)
        pytest.skip(message)
    return connection


@pytest.mark.redis
def test_rq_dispatcher_enqueues_and_worker_consumes(monkeypatch):
    connection = _redis_connection_or_skip()
    queue_name = f"document-test-{uuid4().hex}"
    processed: list[int] = []
    queue = Queue(queue_name, connection=connection)
    monkeypatch.setattr(settings, "REDIS_URL", os.environ["REDIS_URL"])
    monkeypatch.setattr(settings, "DOCUMENT_TASK_QUEUE", queue_name)
    monkeypatch.setattr(worker, "process_document_task", lambda document_id: processed.append(document_id))
    try:
        RQDocumentTaskDispatcher().enqueue(987654)
        SimpleWorker([queue], connection=connection).work(burst=True, logging_level="WARNING")
        assert processed == [987654]
    finally:
        queue.empty()
        connection.delete(queue.key)
