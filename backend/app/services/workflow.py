import json
import logging
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.llm.base import LLMMessage, LLMResponse
from app.llm.factory import get_llm_provider
from app.llm.registry import resolve_model
from app.models.project import Project
from app.models.user import User, utcnow_naive
from app.models.workflow import Approval, Artifact, StepRun, TaskRun
from app.rag.retrieval import RetrievedChunk, retrieve
from app.services.project import (
    _PROJECT_SYSTEM_SAFETY_PROMPT,
    append_project_instructions,
    touch_project_activity,
)
from app.services.billing import charge_response

logger = logging.getLogger(__name__)

WORKFLOW_STEPS = ("research", "summary", "review", "finalize")
_RESEARCH_QUERY = "检索本项目中可用于形成研究总结的相关资料"
_RESEARCH_TOP_K = 5
_UNSET = object()


class WorkflowConflict(Exception):
    """A requested state transition is not valid for the current task."""


class WorkflowNotFound(Exception):
    """The task does not exist or is not owned by the requesting user."""


class WorkflowProjectMissing(RuntimeError):
    """The task project disappeared or is no longer owned by the task user."""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _task_query():
    return select(TaskRun).options(
        selectinload(TaskRun.steps),
        selectinload(TaskRun.approvals),
        selectinload(TaskRun.artifacts),
        selectinload(TaskRun.project),
    )


def _load_task(
    session: Session, user_id: int, task_id: int, *, for_update: bool = False
) -> TaskRun | None:
    statement = (
        _task_query()
        .where(TaskRun.id == task_id, TaskRun.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def create_task(session: Session, user: User, project: Project, title: str | None) -> TaskRun:
    normalized_title = title.strip() if title is not None else f"{project.name}研究"
    if not normalized_title:
        raise ValueError("任务标题不能为空")
    task = TaskRun(
        user_id=user.id,
        project_id=project.id,
        workflow_type="project_research",
        title=normalized_title,
        status="queued",
    )
    task.steps = [StepRun(step_name=name, status="pending") for name in WORKFLOW_STEPS]
    session.add(task)
    session.flush()
    touch_project_activity(session, project.id)
    return task


def get_task(session: Session, user_id: int, task_id: int) -> TaskRun | None:
    return _load_task(session, user_id, task_id)


def list_tasks(
    session: Session, user_id: int, task_status: str | None = None
) -> list[TaskRun]:
    statement = _task_query().where(TaskRun.user_id == user_id)
    if task_status is not None:
        statement = statement.where(TaskRun.status == task_status)
    return list(
        session.scalars(statement.order_by(TaskRun.created_at.desc(), TaskRun.id.desc())).all()
    )


def _step(task: TaskRun, step_name: str) -> StepRun:
    return next(step for step in task.steps if step.step_name == step_name)


def _load_json(raw: str | None) -> dict:
    if not raw:
        return {}
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def _research_output(chunks: Iterable[RetrievedChunk]) -> dict:
    remaining = max(settings.RAG_MAX_CONTEXT_CHARS, 0)
    serialized_chunks: list[dict] = []
    citations: list[dict] = []
    for chunk in chunks:
        if remaining <= 0:
            break
        content = chunk.content[:remaining]
        remaining -= len(content)
        serialized_chunks.append(
            {
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "chunk_index": chunk.chunk_index,
                "content": content,
            }
        )
        citations.append(
            {
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "chunk_index": chunk.chunk_index,
            }
        )
    return {"chunks": serialized_chunks, "citations": citations}


def _complete(messages: list[LLMMessage], user_id: int, session: Session) -> str:
    response = get_llm_provider().complete(messages, model=resolve_model("auto"))
    if response.content is None or not response.content.strip():
        raise RuntimeError("LLM 返回空内容")
    charge_response(session, user_id, response, "auto", "workflow step", kind="workflow")
    return response.content.strip()


def _project_exists_for_task(session: Session, task: TaskRun, *, lock: bool = False) -> bool:
    if task.project_id is None:
        return False
    statement = select(Project.id).where(
        Project.id == task.project_id,
        Project.user_id == task.user_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement) is not None


def _require_project(session: Session, task: TaskRun, *, lock: bool = False) -> None:
    if not _project_exists_for_task(session, task, lock=lock):
        raise WorkflowConflict("任务关联项目不存在或不属于任务用户")


def _execute_research(session: Session, task: TaskRun) -> tuple[dict, dict]:
    if not _project_exists_for_task(session, task):
        raise WorkflowProjectMissing("project missing")
    top_k = min(_RESEARCH_TOP_K, 20)
    structured_input = {
        "query": _RESEARCH_QUERY,
        "top_k": top_k,
        "project_id": task.project_id,
    }
    chunks = retrieve(
        session,
        task.user_id,
        _RESEARCH_QUERY,
        top_k=top_k,
        project_id=task.project_id,
    )
    return structured_input, _research_output(chunks)


def _execute_summary(session: Session, task: TaskRun) -> tuple[dict, dict]:
    research = _load_json(_step(task, "research").structured_output)
    system_prompt = append_project_instructions(
        _PROJECT_SYSTEM_SAFETY_PROMPT,
        task.project.instructions if task.project is not None else None,
    )
    system_prompt = f"{system_prompt}\n\n输出结构化总结，并明确区分事实、结论与引用。"
    content = _complete(
        [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=_json(research)),
        ], task.user_id, session
    )
    return research, {"summary": content}


def _execute_review(session: Session, task: TaskRun) -> tuple[dict, dict]:
    summary = _load_json(_step(task, "summary").structured_output)
    research = _load_json(_step(task, "research").structured_output)
    review_input = {
        "summary": summary.get("summary", ""),
        "citations": research.get("citations", []),
    }
    content = _complete(
        [
            LLMMessage(
                role="system",
                content=(
                    f"{_PROJECT_SYSTEM_SAFETY_PROMPT}\n\n"
                    "检查总结是否有来源支撑、是否存在遗漏，并输出检查结果与引用。"
                ),
            ),
            LLMMessage(role="user", content=_json(review_input)),
        ], task.user_id, session
    )
    return review_input, {
        "review": content,
        "citations": research.get("citations", []),
    }


def _execute_finalize(task: TaskRun) -> tuple[dict, dict, dict]:
    summary = _load_json(_step(task, "summary").structured_output).get("summary", "")
    review_output = _load_json(_step(task, "review").structured_output)
    review = review_output.get("review", "")
    citations = review_output.get("citations", [])
    structured_input = {
        "summary_step": "summary",
        "review_step": "review",
        "citation_count": len(citations),
    }
    artifact_values = {
        "task_run_id": task.id,
        "artifact_type": "project_research",
        "title": task.title,
        "content": (
            f"## 总结\n\n{summary}\n\n"
            f"## 审查\n\n{review}\n\n"
            f"## 引用\n\n{_json(citations)}"
        ),
        "metadata_json": _json(
            {
                "workflow_type": task.workflow_type,
                "citation_count": len(citations),
                "document_ids": sorted(
                    {item["document_id"] for item in citations if "document_id" in item}
                ),
            }
        ),
    }
    output = {
        "artifact_type": artifact_values["artifact_type"],
        "citation_count": len(citations),
    }
    return structured_input, output, artifact_values


def _transition_miss(
    session: Session, user_id: int, task_id: int, conflict_message: str
) -> None:
    owned = session.scalar(
        select(TaskRun.id).where(TaskRun.id == task_id, TaskRun.user_id == user_id)
    )
    if owned is None:
        raise WorkflowNotFound("任务不存在")
    raise WorkflowConflict(conflict_message)


def _conditional_task_update(
    session: Session,
    *,
    user_id: int,
    task_id: int,
    expected_status: str | set[str],
    values: dict,
    conflict_message: str,
    expected_current_step: str | None | object = _UNSET,
    expected_updated_at: datetime | object = _UNSET,
) -> None:
    statuses = {expected_status} if isinstance(expected_status, str) else expected_status
    conditions = [
        TaskRun.id == task_id,
        TaskRun.user_id == user_id,
        TaskRun.status.in_(statuses),
    ]
    if expected_current_step is not _UNSET:
        if expected_current_step is None:
            conditions.append(TaskRun.current_step.is_(None))
        else:
            conditions.append(TaskRun.current_step == expected_current_step)
    if expected_updated_at is not _UNSET:
        conditions.append(TaskRun.updated_at == expected_updated_at)
    result = session.execute(
        update(TaskRun)
        .where(*conditions)
        .values(**values),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        _transition_miss(session, user_id, task_id, conflict_message)


def _conditional_step_update(
    session: Session,
    *,
    user_id: int,
    task_id: int,
    step_id: int,
    expected_status: str,
    expected_attempt: int,
    values: dict,
    conflict_message: str,
) -> None:
    result = session.execute(
        update(StepRun)
        .where(
            StepRun.id == step_id,
            StepRun.task_run_id == task_id,
            StepRun.status == expected_status,
            StepRun.attempt == expected_attempt,
        )
        .values(**values),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        _transition_miss(session, user_id, task_id, conflict_message)


def _claim_step(
    session: Session,
    *,
    user_id: int,
    task_id: int,
    step_name: str,
    expected_status: str | None = None,
    expected_attempt: int | None = None,
) -> tuple[TaskRun, int, datetime]:
    task = _load_task(session, user_id, task_id, for_update=True)
    if task is None:
        raise WorkflowNotFound("任务不存在")
    step = _step(task, step_name)
    step_status = step.status if expected_status is None else expected_status
    step_attempt = step.attempt if expected_attempt is None else expected_attempt
    attempted = step_attempt + 1
    now = utcnow_naive()

    _conditional_task_update(
        session,
        user_id=user_id,
        task_id=task_id,
        expected_status="running",
        values={
            "status": "running",
            "current_step": step_name,
            "error": None,
            "completed_at": None,
            "started_at": task.started_at or now,
            "updated_at": now,
        },
        conflict_message="任务已被其他请求更新，当前步骤不能执行",
    )
    _conditional_step_update(
        session,
        user_id=user_id,
        task_id=task_id,
        step_id=step.id,
        expected_status=step_status,
        expected_attempt=step_attempt,
        values={
            "status": "running",
            "attempt": attempted,
            "error": None,
            "started_at": now,
            "completed_at": None,
        },
        conflict_message=f"{step_name} 步骤已被其他请求执行",
    )
    session.commit()
    claimed = _load_task(session, user_id, task_id)
    if claimed is None:
        raise WorkflowNotFound("任务不存在")
    return claimed, attempted, now


def _complete_step(
    session: Session,
    *,
    user_id: int,
    task_id: int,
    step_name: str,
    attempted: int,
    structured_input: dict,
    output: dict,
    artifact_values: dict | None = None,
) -> TaskRun:
    task = _load_task(session, user_id, task_id, for_update=True)
    if task is None:
        raise WorkflowNotFound("任务不存在")
    step = _step(task, step_name)
    completed_at = utcnow_naive()

    if step_name == "review":
        existing_approval = session.scalar(
            select(Approval.id).where(
                Approval.task_run_id == task_id,
                Approval.status.not_in(("approved", "rejected")),
            )
        )
        if existing_approval is not None:
            raise WorkflowConflict("任务已存在未完成的审批")

    existing_artifact = None
    if step_name == "finalize":
        existing_artifact = session.scalar(
            select(Artifact).where(
                Artifact.task_run_id == task_id,
                Artifact.artifact_type == "project_research",
            )
        )

    _conditional_step_update(
        session,
        user_id=user_id,
        task_id=task_id,
        step_id=step.id,
        expected_status="running",
        expected_attempt=attempted,
        values={
            "structured_input": _json(structured_input),
            "structured_output": _json(output),
            "status": "succeeded",
            "error": None,
            "completed_at": completed_at,
        },
        conflict_message=f"{step_name} 步骤结果已过期",
    )

    task_values: dict = {"updated_at": completed_at}
    if step_name == "review":
        task_values.update(status="waiting_approval", current_step="review")
    elif step_name == "finalize":
        task_values.update(
            status="succeeded",
            current_step=None,
            completed_at=completed_at,
            error=None,
        )
    _conditional_task_update(
        session,
        user_id=user_id,
        task_id=task_id,
        expected_status="running",
        expected_current_step=step_name,
        values=task_values,
        conflict_message="任务已被其他请求更新，步骤结果不能保存",
    )

    if step_name == "review":
        session.add(
            Approval(
                task_run_id=task_id,
                requested_by_step="review",
                status="pending",
            )
        )
    elif step_name == "finalize" and existing_artifact is None:
        if artifact_values is None:
            raise RuntimeError("finalize artifact payload missing")
        session.add(Artifact(**artifact_values))

    session.flush()
    session.commit()
    completed = _load_task(session, user_id, task_id)
    if completed is None:
        raise WorkflowNotFound("任务不存在")
    return completed


def _safe_step_error(step_name: str, exc: Exception) -> str:
    if isinstance(exc, WorkflowProjectMissing):
        return f"{step_name} 步骤执行失败（项目不存在或无权访问）"
    return f"{step_name} 步骤执行失败（{type(exc).__name__}）"


def _mark_step_failed(
    session: Session,
    *,
    user_id: int,
    task_id: int,
    step_name: str,
    attempted: int,
    exc: Exception,
) -> TaskRun:
    session.rollback()
    task = _load_task(session, user_id, task_id, for_update=True)
    if task is None:
        raise WorkflowNotFound("任务不存在") from exc
    step = _step(task, step_name)
    safe_error = _safe_step_error(step_name, exc)
    now = utcnow_naive()
    _conditional_step_update(
        session,
        user_id=user_id,
        task_id=task_id,
        step_id=step.id,
        expected_status="running",
        expected_attempt=attempted,
        values={
            "status": "failed",
            "error": safe_error,
            "completed_at": now,
        },
        conflict_message=f"{step_name} 步骤失败结果已过期",
    )
    _conditional_task_update(
        session,
        user_id=user_id,
        task_id=task_id,
        expected_status="running",
        expected_current_step=step_name,
        values={
            "status": "failed",
            "current_step": step_name,
            "error": safe_error,
            "completed_at": now,
            "updated_at": now,
        },
        conflict_message="任务已被其他请求更新，失败结果不能保存",
    )
    session.commit()
    logger.warning(
        "workflow step failed task_id=%s step=%s error_type=%s",
        task_id,
        step_name,
        type(exc).__name__,
    )
    failed = _load_task(session, user_id, task_id)
    if failed is None:
        raise WorkflowNotFound("任务不存在") from exc
    return failed


def _run_step(
    session: Session,
    task: TaskRun,
    step_name: str,
    *,
    expected_status: str | None = None,
    expected_attempt: int | None = None,
) -> tuple[TaskRun, bool]:
    task, attempted, _ = _claim_step(
        session,
        user_id=task.user_id,
        task_id=task.id,
        step_name=step_name,
        expected_status=expected_status,
        expected_attempt=expected_attempt,
    )

    artifact_values = None
    try:
        if step_name == "research":
            structured_input, output = _execute_research(session, task)
        elif step_name == "summary":
            structured_input, output = _execute_summary(session, task)
        elif step_name == "review":
            structured_input, output = _execute_review(session, task)
        elif step_name == "finalize":
            structured_input, output, artifact_values = _execute_finalize(task)
        else:
            raise RuntimeError("未知工作流步骤")
    except Exception as exc:
        return (
            _mark_step_failed(
                session,
                user_id=task.user_id,
                task_id=task.id,
                step_name=step_name,
                attempted=attempted,
                exc=exc,
            ),
            False,
        )

    try:
        completed = _complete_step(
            session,
            user_id=task.user_id,
            task_id=task.id,
            step_name=step_name,
            attempted=attempted,
            structured_input=structured_input,
            output=output,
            artifact_values=artifact_values,
        )
    except Exception:
        session.rollback()
        raise
    return completed, True


def _execute_from(
    session: Session,
    task: TaskRun,
    first_step: str,
    *,
    first_expected_status: str | None = None,
    first_expected_attempt: int | None = None,
) -> TaskRun:
    if first_step == "finalize":
        task, _ = _run_step(
            session,
            task,
            "finalize",
            expected_status=first_expected_status,
            expected_attempt=first_expected_attempt,
        )
        return task
    start_index = WORKFLOW_STEPS.index(first_step)
    for index, step_name in enumerate(WORKFLOW_STEPS[start_index:]):
        if step_name == "finalize":
            break
        task, succeeded = _run_step(
            session,
            task,
            step_name,
            expected_status=first_expected_status if index == 0 else None,
            expected_attempt=first_expected_attempt if index == 0 else None,
        )
        if not succeeded or task.status == "waiting_approval":
            return task
    return task


def start_task(session: Session, task: TaskRun) -> TaskRun:
    locked = _load_task(session, task.user_id, task.id, for_update=True)
    if locked is None:
        raise WorkflowNotFound("任务不存在")
    _require_project(session, locked, lock=True)
    now = utcnow_naive()
    _conditional_task_update(
        session,
        user_id=task.user_id,
        task_id=task.id,
        expected_status="queued",
        values={
            "status": "running",
            "current_step": "research",
            "started_at": now,
            "completed_at": None,
            "error": None,
            "updated_at": now,
        },
        conflict_message="只有排队中的任务可以开始，不能重复启动",
    )
    running = _load_task(session, task.user_id, task.id)
    if running is None:
        raise WorkflowNotFound("任务不存在")
    return _execute_from(
        session,
        running,
        "research",
        first_expected_status="pending",
        first_expected_attempt=0,
    )


def cancel_task(session: Session, task: TaskRun) -> TaskRun:
    now = utcnow_naive()
    _conditional_task_update(
        session,
        user_id=task.user_id,
        task_id=task.id,
        expected_status={"queued", "running"},
        values={
            "status": "cancelled",
            "completed_at": now,
            "current_step": None,
            "updated_at": now,
        },
        conflict_message="当前任务状态不能取消",
    )
    cancelled = _load_task(session, task.user_id, task.id)
    if cancelled is None:
        raise WorkflowNotFound("任务不存在")
    return cancelled


def retry_task(session: Session, task: TaskRun) -> TaskRun:
    expected_task_status = task.status
    expected_current_step = task.current_step
    expected_updated_at = task.updated_at
    if expected_task_status not in {"failed", "running"}:
        raise WorkflowConflict("只有失败或运行中断的任务可以重试")

    step_name = (
        expected_current_step
        if expected_current_step in WORKFLOW_STEPS
        else "research"
    )
    retry_step = _step(task, step_name)
    expected_step_status = retry_step.status
    expected_step_attempt = retry_step.attempt
    if expected_step_attempt >= settings.WORKFLOW_MAX_STEP_ATTEMPTS:
        raise WorkflowConflict(f"{step_name} 步骤已达到最大尝试次数")

    locked = _load_task(session, task.user_id, task.id, for_update=True)
    if locked is None:
        raise WorkflowNotFound("任务不存在")
    _require_project(session, locked, lock=True)
    now = utcnow_naive()
    _conditional_task_update(
        session,
        user_id=task.user_id,
        task_id=task.id,
        expected_status=expected_task_status,
        expected_current_step=expected_current_step,
        expected_updated_at=expected_updated_at,
        values={
            "status": "running",
            "current_step": step_name,
            "error": None,
            "completed_at": None,
            "updated_at": now,
        },
        conflict_message="任务已被其他请求恢复或状态已变化",
    )
    running = _load_task(session, task.user_id, task.id)
    if running is None:
        raise WorkflowNotFound("任务不存在")
    return _execute_from(
        session,
        running,
        step_name,
        first_expected_status=expected_step_status,
        first_expected_attempt=expected_step_attempt,
    )


def _pending_approval(task: TaskRun) -> Approval:
    approvals = [item for item in task.approvals if item.status == "pending"]
    if len(approvals) != 1:
        raise WorkflowConflict("任务没有唯一的待处理审批")
    return approvals[0]


def approve_task(session: Session, task: TaskRun, comment: str | None) -> TaskRun:
    locked = _load_task(session, task.user_id, task.id, for_update=True)
    if locked is None:
        raise WorkflowNotFound("任务不存在")
    approval = _pending_approval(locked)
    now = utcnow_naive()
    _conditional_task_update(
        session,
        user_id=task.user_id,
        task_id=task.id,
        expected_status="waiting_approval",
        values={
            "status": "running",
            "current_step": "finalize",
            "completed_at": None,
            "error": None,
            "updated_at": now,
        },
        conflict_message="只有等待审批的任务可以批准",
    )
    result = session.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.task_run_id == task.id,
            Approval.status == "pending",
        )
        .values(status="approved", comment=comment, decided_at=now),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        raise WorkflowConflict("审批已被其他请求处理")
    session.commit()
    running = _load_task(session, task.user_id, task.id)
    if running is None:
        raise WorkflowNotFound("任务不存在")
    finalize = _step(running, "finalize")
    return _execute_from(
        session,
        running,
        "finalize",
        first_expected_status=finalize.status,
        first_expected_attempt=finalize.attempt,
    )


def reject_task(session: Session, task: TaskRun, comment: str | None) -> TaskRun:
    locked = _load_task(session, task.user_id, task.id, for_update=True)
    if locked is None:
        raise WorkflowNotFound("任务不存在")
    approval = _pending_approval(locked)
    now = utcnow_naive()
    _conditional_task_update(
        session,
        user_id=task.user_id,
        task_id=task.id,
        expected_status="waiting_approval",
        values={
            "status": "cancelled",
            "current_step": None,
            "completed_at": now,
            "updated_at": now,
        },
        conflict_message="只有等待审批的任务可以拒绝",
    )
    result = session.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.task_run_id == task.id,
            Approval.status == "pending",
        )
        .values(status="rejected", comment=comment, decided_at=now),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount != 1:
        raise WorkflowConflict("审批已被其他请求处理")
    rejected = _load_task(session, task.user_id, task.id)
    if rejected is None:
        raise WorkflowNotFound("任务不存在")
    return rejected
