import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.llm.base import LLMResponse
from app.main import app
from app.models.workflow import Approval, Artifact, StepRun, TaskRun
from app.rag.retrieval import RetrievedChunk
from app.services import workflow


class FakeWorkflowProvider:
    def __init__(self):
        self.calls = []
        self.fail_on_calls: set[int] = set()

    def complete(self, messages, *, model=None):
        call_number = len(self.calls) + 1
        self.calls.append({"messages": list(messages), "model": model})
        if call_number in self.fail_on_calls:
            raise RuntimeError("api-key=super-secret token=private-token full sensitive content")
        content = "结构化总结" if call_number % 2 else "审查通过并保留引用"
        return LLMResponse(content=content, model="fake-workflow-model")


@pytest.fixture()
def fake_workflow(monkeypatch):
    provider = FakeWorkflowProvider()
    calls = []

    def fake_retrieve(session, user_id, query, top_k, project_id=None):
        calls.append(
            {
                "user_id": user_id,
                "query": query,
                "top_k": top_k,
                "project_id": project_id,
            }
        )
        return [
            RetrievedChunk(
                document_id=91,
                filename="project-only.txt",
                chunk_index=3,
                content="E" * (settings.RAG_MAX_CONTEXT_CHARS + 100),
                score=0.99,
            )
        ]

    monkeypatch.setattr(workflow, "get_llm_provider", lambda: provider)
    monkeypatch.setattr(workflow, "retrieve", fake_retrieve)
    return provider, calls


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
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    ).json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_project(client, token: str, name="研究项目", instructions="只使用项目资料"):
    return client.post(
        "/api/projects",
        json={"name": name, "instructions": instructions},
        headers=_auth(token),
    ).json()


def _create_task(client, token: str, project_id: int, title="调研任务"):
    return client.post(
        "/api/tasks",
        json={"project_id": project_id, "title": title},
        headers=_auth(token),
    )


def test_workflow_happy_path_persists_steps_approval_and_artifact(
    client, db, fake_workflow
):
    provider, retrieval_calls = fake_workflow
    token = _register_and_login(client, "alice")
    project = _create_project(client, token)
    created = _create_task(client, token, project["id"])

    assert created.status_code == 201
    task = created.json()
    assert task["status"] == "queued"
    assert [step["step_name"] for step in task["steps"]] == [
        "research",
        "summary",
        "review",
        "finalize",
    ]

    started = client.post(f"/api/tasks/{task['id']}/start", headers=_auth(token))
    assert started.status_code == 200
    waiting = started.json()
    assert waiting["status"] == "waiting_approval"
    assert [step["status"] for step in waiting["steps"]] == [
        "succeeded",
        "succeeded",
        "succeeded",
        "pending",
    ]
    assert [step["attempt"] for step in waiting["steps"]] == [1, 1, 1, 0]
    assert waiting["approvals"][0]["status"] == "pending"
    assert retrieval_calls[0]["project_id"] == project["id"]
    assert retrieval_calls[0]["user_id"] == db.get(TaskRun, task["id"]).user_id

    research = json.loads(waiting["steps"][0]["structured_output"])
    assert len(research["chunks"][0]["content"]) == settings.RAG_MAX_CONTEXT_CHARS
    summary_prompt = provider.calls[0]["messages"][0].content
    assert summary_prompt.index("Follow all system-level safety") < summary_prompt.index(
        "只使用项目资料"
    ) < summary_prompt.index("输出结构化总结")
    assert "检查总结是否有来源支撑" in provider.calls[1]["messages"][0].content

    approved = client.post(
        f"/api/tasks/{task['id']}/approve",
        json={"comment": "批准生成"},
        headers=_auth(token),
    )
    assert approved.status_code == 200
    succeeded = approved.json()
    assert succeeded["status"] == "succeeded"
    assert succeeded["current_step"] is None
    assert succeeded["approvals"][0]["status"] == "approved"
    assert succeeded["steps"][-1]["status"] == "succeeded"
    assert len(succeeded["artifacts"]) == 1
    assert succeeded["artifacts"][0]["artifact_type"] == "project_research"
    assert "结构化总结" in succeeded["artifacts"][0]["content"]
    assert "审查通过" in succeeded["artifacts"][0]["content"]
    assert json.loads(succeeded["artifacts"][0]["metadata"])["document_ids"] == [91]

    artifacts = client.get(
        f"/api/tasks/{task['id']}/artifacts", headers=_auth(token)
    )
    assert artifacts.status_code == 200
    assert artifacts.json()[0]["id"] == succeeded["artifacts"][0]["id"]
    assert db.query(Artifact).filter_by(task_run_id=task["id"]).count() == 1


def test_workflow_ownership_is_hidden_and_project_must_be_owned(client, fake_workflow):
    alice = _register_and_login(client, "alice")
    bob = _register_and_login(client, "bob")
    project = _create_project(client, alice)
    task = _create_task(client, alice, project["id"]).json()

    assert _create_task(client, bob, project["id"]).status_code == 404
    for method, suffix, body in [
        ("get", "", None),
        ("post", "/start", None),
        ("post", "/cancel", None),
        ("post", "/retry", None),
        ("post", "/approve", {}),
        ("post", "/reject", {}),
        ("get", "/artifacts", None),
    ]:
        response = client.request(
            method.upper(),
            f"/api/tasks/{task['id']}{suffix}", json=body, headers=_auth(bob)
        )
        assert response.status_code == 404


def test_workflow_state_guards_filtering_cancel_and_reject(client, fake_workflow):
    token = _register_and_login(client, "alice")
    project = _create_project(client, token)
    queued = _create_task(client, token, project["id"], "取消任务").json()
    cancelled = client.post(
        f"/api/tasks/{queued['id']}/cancel", headers=_auth(token)
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(
        f"/api/tasks/{queued['id']}/cancel", headers=_auth(token)
    ).status_code == 409
    assert client.post(
        f"/api/tasks/{queued['id']}/start", headers=_auth(token)
    ).status_code == 409

    task = _create_task(client, token, project["id"], "拒绝任务").json()
    assert client.post(f"/api/tasks/{task['id']}/start", headers=_auth(token)).status_code == 200
    assert client.post(
        f"/api/tasks/{task['id']}/start", headers=_auth(token)
    ).status_code == 409
    assert client.post(
        f"/api/tasks/{task['id']}/cancel", headers=_auth(token)
    ).status_code == 409
    rejected = client.post(
        f"/api/tasks/{task['id']}/reject",
        json={"comment": "资料不足"},
        headers=_auth(token),
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "cancelled"
    assert rejected.json()["approvals"][0]["status"] == "rejected"
    assert client.post(
        f"/api/tasks/{task['id']}/approve", json={}, headers=_auth(token)
    ).status_code == 409

    listed = client.get("/api/tasks?status=cancelled", headers=_auth(token))
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {queued["id"], task["id"]}
    assert client.get("/api/tasks?status=invalid", headers=_auth(token)).status_code == 422


def test_failed_step_is_persisted_and_retry_resumes_with_attempt_increment(
    client, db, fake_workflow
):
    provider, _ = fake_workflow
    provider.fail_on_calls = {1}
    token = _register_and_login(client, "alice")
    project = _create_project(client, token)
    task = _create_task(client, token, project["id"]).json()

    failed = client.post(f"/api/tasks/{task['id']}/start", headers=_auth(token))
    assert failed.status_code == 200
    body = failed.json()
    assert body["status"] == "failed"
    assert body["current_step"] == "summary"
    summary = next(step for step in body["steps"] if step["step_name"] == "summary")
    assert summary["status"] == "failed"
    assert summary["attempt"] == 1
    assert summary["error"]
    assert db.get(StepRun, summary["id"]).error == summary["error"]

    provider.fail_on_calls.clear()
    retried = client.post(f"/api/tasks/{task['id']}/retry", headers=_auth(token))
    assert retried.status_code == 200
    body = retried.json()
    assert body["status"] == "waiting_approval"
    summary = next(step for step in body["steps"] if step["step_name"] == "summary")
    assert summary["attempt"] == 2
    assert summary["status"] == "succeeded"
    assert client.post(f"/api/tasks/{task['id']}/retry", headers=_auth(token)).status_code == 409


def test_retry_limit_keeps_task_failed_with_error(client, fake_workflow, monkeypatch):
    provider, _ = fake_workflow
    provider.fail_on_calls = {1, 2}
    monkeypatch.setattr(settings, "WORKFLOW_MAX_STEP_ATTEMPTS", 2)
    token = _register_and_login(client, "alice")
    project = _create_project(client, token)
    task = _create_task(client, token, project["id"]).json()

    client.post(f"/api/tasks/{task['id']}/start", headers=_auth(token))
    second_failure = client.post(
        f"/api/tasks/{task['id']}/retry", headers=_auth(token)
    ).json()
    summary = next(
        step for step in second_failure["steps"] if step["step_name"] == "summary"
    )
    assert summary["attempt"] == 2
    assert second_failure["status"] == "failed"

    over_limit = client.post(
        f"/api/tasks/{task['id']}/retry", headers=_auth(token)
    )
    assert over_limit.status_code == 409
    assert "最大尝试次数" in over_limit.json()["detail"]
    persisted = client.get(f"/api/tasks/{task['id']}", headers=_auth(token)).json()
    assert persisted["status"] == "failed"
    assert next(
        step for step in persisted["steps"] if step["step_name"] == "summary"
    )["attempt"] == 2


@pytest.mark.parametrize(
    ("current_step", "step_status", "initial_attempt", "expected_attempt"),
    [
        ("research", "running", 1, 2),
        (None, "pending", 0, 1),
    ],
)
def test_retry_recovers_running_task_from_current_or_research(
    client,
    db,
    fake_workflow,
    current_step,
    step_status,
    initial_attempt,
    expected_attempt,
):
    _, retrieval_calls = fake_workflow
    token = _register_and_login(client, f"recover-{expected_attempt}")
    project = _create_project(client, token)
    task_body = _create_task(client, token, project["id"]).json()
    task = db.get(TaskRun, task_body["id"])
    research = next(step for step in task.steps if step.step_name == "research")
    task.status = "running"
    task.current_step = current_step
    research.status = step_status
    research.attempt = initial_attempt
    db.commit()

    recovered = client.post(
        f"/api/tasks/{task.id}/retry", headers=_auth(token)
    )

    assert recovered.status_code == 200
    body = recovered.json()
    assert body["status"] == "waiting_approval"
    assert next(
        step for step in body["steps"] if step["step_name"] == "research"
    )["attempt"] == expected_attempt
    assert retrieval_calls == [
        {
            "user_id": task.user_id,
            "query": workflow._RESEARCH_QUERY,
            "top_k": 5,
            "project_id": project["id"],
        }
    ]


def test_project_is_rechecked_for_start_and_retry_but_not_finalize(
    client, fake_workflow
):
    provider, _ = fake_workflow
    token = _register_and_login(client, "project-recheck")

    queued_project = _create_project(client, token, name="queued-project")
    queued_task = _create_task(client, token, queued_project["id"]).json()
    assert client.delete(
        f"/api/projects/{queued_project['id']}", headers=_auth(token)
    ).status_code == 204
    start = client.post(
        f"/api/tasks/{queued_task['id']}/start", headers=_auth(token)
    )
    assert start.status_code == 409
    assert "项目" in start.json()["detail"]

    failed_project = _create_project(client, token, name="failed-project")
    failed_task = _create_task(client, token, failed_project["id"]).json()
    provider.fail_on_calls = {1}
    assert client.post(
        f"/api/tasks/{failed_task['id']}/start", headers=_auth(token)
    ).json()["status"] == "failed"
    assert client.delete(
        f"/api/projects/{failed_project['id']}", headers=_auth(token)
    ).status_code == 204
    retry = client.post(
        f"/api/tasks/{failed_task['id']}/retry", headers=_auth(token)
    )
    assert retry.status_code == 409
    assert "项目" in retry.json()["detail"]

    provider.fail_on_calls.clear()
    final_project = _create_project(client, token, name="final-project")
    final_task = _create_task(client, token, final_project["id"]).json()
    waiting = client.post(
        f"/api/tasks/{final_task['id']}/start", headers=_auth(token)
    )
    assert waiting.json()["status"] == "waiting_approval"
    assert client.delete(
        f"/api/projects/{final_project['id']}", headers=_auth(token)
    ).status_code == 204

    approved = client.post(
        f"/api/tasks/{final_task['id']}/approve",
        json={"comment": "项目删除后仍完成"},
        headers=_auth(token),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "succeeded"
    assert len(approved.json()["artifacts"]) == 1


def test_finalize_reuses_existing_artifact(client, db, fake_workflow):
    token = _register_and_login(client, "artifact-reuse")
    project = _create_project(client, token)
    task = _create_task(client, token, project["id"]).json()
    assert client.post(
        f"/api/tasks/{task['id']}/start", headers=_auth(token)
    ).json()["status"] == "waiting_approval"
    db.add(
        Artifact(
            task_run_id=task["id"],
            artifact_type="project_research",
            title="已持久化产物",
            content="durable artifact",
            metadata_json="{}",
        )
    )
    db.commit()

    approved = client.post(
        f"/api/tasks/{task['id']}/approve", json={}, headers=_auth(token)
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "succeeded"
    assert len(approved.json()["artifacts"]) == 1
    assert approved.json()["artifacts"][0]["content"] == "durable artifact"
    assert db.query(Artifact).filter_by(task_run_id=task["id"]).count() == 1


def test_concurrent_start_and_approve_have_single_winner_and_execution(
    tmp_path, fake_workflow, monkeypatch
):
    provider, retrieval_calls = fake_workflow
    database_path = tmp_path / "workflow-concurrency.sqlite3"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    concurrency_session = sessionmaker(
        bind=engine, autocommit=False, autoflush=False
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        session = concurrency_session()
        try:
            yield session
        finally:
            session.close()

    original_retrieve = workflow.retrieve
    start_entered = Event()
    release_start = Event()

    def blocking_retrieve(*args, **kwargs):
        start_entered.set()
        assert release_start.wait(timeout=10)
        return original_retrieve(*args, **kwargs)

    monkeypatch.setattr(workflow, "retrieve", blocking_retrieve)
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as concurrent_client:
            token = _register_and_login(concurrent_client, "concurrent")
            project = _create_project(concurrent_client, token)
            task = _create_task(concurrent_client, token, project["id"]).json()

            with ThreadPoolExecutor(max_workers=2) as executor:
                first_start = executor.submit(
                    concurrent_client.post,
                    f"/api/tasks/{task['id']}/start",
                    headers=_auth(token),
                )
                assert start_entered.wait(timeout=10)
                second_start = executor.submit(
                    concurrent_client.post,
                    f"/api/tasks/{task['id']}/start",
                    headers=_auth(token),
                )
                second_start_response = second_start.result(timeout=10)
                release_start.set()
                first_start_response = first_start.result(timeout=10)

            assert sorted(
                [first_start_response.status_code, second_start_response.status_code]
            ) == [200, 409]
            assert first_start_response.json()["status"] == "waiting_approval"
            assert len(retrieval_calls) == 1
            assert len(provider.calls) == 2

            original_finalize = workflow._execute_finalize
            finalize_entered = Event()
            release_finalize = Event()

            def blocking_finalize(*args, **kwargs):
                finalize_entered.set()
                assert release_finalize.wait(timeout=10)
                return original_finalize(*args, **kwargs)

            monkeypatch.setattr(workflow, "_execute_finalize", blocking_finalize)
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_approve = executor.submit(
                    concurrent_client.post,
                    f"/api/tasks/{task['id']}/approve",
                    headers=_auth(token),
                    json={},
                )
                assert finalize_entered.wait(timeout=10)
                second_approve = executor.submit(
                    concurrent_client.post,
                    f"/api/tasks/{task['id']}/approve",
                    headers=_auth(token),
                    json={},
                )
                second_approve_response = second_approve.result(timeout=10)
                release_finalize.set()
                first_approve_response = first_approve.result(timeout=10)

            assert sorted(
                [first_approve_response.status_code, second_approve_response.status_code]
            ) == [200, 409]
            assert first_approve_response.json()["status"] == "succeeded"

        with concurrency_session() as session:
            assert session.query(Approval).filter_by(task_run_id=task["id"]).count() == 1
            assert session.query(Artifact).filter_by(task_run_id=task["id"]).count() == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def test_workflow_logs_do_not_contain_provider_secrets(
    client, fake_workflow, caplog
):
    provider, _ = fake_workflow
    provider.fail_on_calls = {1}
    token = _register_and_login(client, "alice")
    project = _create_project(client, token)
    task = _create_task(client, token, project["id"]).json()

    with caplog.at_level(logging.WARNING, logger="app.services.workflow"):
        response = client.post(
            f"/api/tasks/{task['id']}/start", headers=_auth(token)
        )

    assert response.json()["status"] == "failed"
    combined = caplog.text + response.text
    assert "super-secret" not in combined
    assert "private-token" not in combined
    assert "full sensitive content" not in combined
    assert "api-key=" not in combined


def test_workflow_models_and_migration_match_contract():
    task_foreign_keys = {
        key.column.table.name: key.ondelete for key in TaskRun.__table__.foreign_keys
    }
    assert task_foreign_keys == {"users": "CASCADE", "projects": "SET NULL"}
    assert next(iter(StepRun.__table__.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(Artifact.__table__.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(Approval.__table__.foreign_keys)).ondelete == "CASCADE"
    assert TaskRun.workflow_type.default.arg == "project_research"
    assert StepRun.attempt.default.arg == 0
    assert Approval.status.default.arg == "pending"

    unique_constraints = {
        constraint.name for constraint in StepRun.__table__.constraints if constraint.name
    }
    assert "uq_step_runs_task_step" in unique_constraints
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "f3a4b5c6d7e8_add_workflow_runs.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: Union[str, None] = "e2f3a4b5c6d7"' in migration
    for table in ("task_runs", "step_runs", "artifacts", "approvals"):
        assert f'"{table}"' in migration
    assert '"mysql_engine": "InnoDB"' in migration
