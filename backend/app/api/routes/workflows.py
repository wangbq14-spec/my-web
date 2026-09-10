from collections.abc import Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.workflow import TaskRun
from app.schemas.workflow import (
    ApprovalDecision,
    ArtifactOut,
    TaskCreate,
    TaskRunOut,
    TaskStatus,
)
from app.services import project as project_service
from app.services import workflow as workflow_service
from app.services.billing import InsufficientCredits, require_balance

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")


def _task_or_404(db: Session, user_id: int, task_id: int) -> TaskRun:
    task = workflow_service.get_task(db, user_id, task_id)
    if task is None:
        raise _not_found()
    return task


def _run_transition(
    db: Session,
    task: TaskRun,
    transition: Callable[..., TaskRun],
    *args,
) -> TaskRun:
    try:
        require_balance(db, task.user_id)
        transition(db, task, *args)
        db.commit()
        refreshed = workflow_service.get_task(db, task.user_id, task.id)
        if refreshed is None:
            raise _not_found()
        return refreshed
    except workflow_service.WorkflowNotFound as exc:
        db.rollback()
        raise _not_found() from exc
    except InsufficientCredits as exc:
        db.rollback()
        raise HTTPException(status_code=402, detail="积分不足") from exc
    except workflow_service.WorkflowConflict as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="任务状态保存失败",
        ) from exc


@router.post("", response_model=TaskRunOut, status_code=status.HTTP_201_CREATED)
def create_task(
    data: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRun:
    project = project_service.get_project(db, current_user, data.project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    try:
        task = workflow_service.create_task(db, current_user, project, data.title)
        db.commit()
        refreshed = workflow_service.get_task(db, current_user.id, task.id)
        if refreshed is None:
            raise _not_found()
        return refreshed
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="任务创建失败"
        ) from exc


@router.get("", response_model=list[TaskRunOut])
def list_tasks(
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TaskRun]:
    return workflow_service.list_tasks(db, current_user.id, task_status)


@router.get("/{task_id}", response_model=TaskRunOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRun:
    return _task_or_404(db, current_user.id, task_id)


@router.post("/{task_id}/start", response_model=TaskRunOut)
def start_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRun:
    return _run_transition(
        db,
        _task_or_404(db, current_user.id, task_id),
        workflow_service.start_task,
    )


@router.post("/{task_id}/cancel", response_model=TaskRunOut)
def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRun:
    return _run_transition(
        db,
        _task_or_404(db, current_user.id, task_id),
        workflow_service.cancel_task,
    )


@router.post("/{task_id}/retry", response_model=TaskRunOut)
def retry_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRun:
    return _run_transition(
        db,
        _task_or_404(db, current_user.id, task_id),
        workflow_service.retry_task,
    )


@router.post("/{task_id}/approve", response_model=TaskRunOut)
def approve_task(
    task_id: int,
    data: ApprovalDecision = Body(default=ApprovalDecision()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRun:
    return _run_transition(
        db,
        _task_or_404(db, current_user.id, task_id),
        workflow_service.approve_task,
        data.comment,
    )


@router.post("/{task_id}/reject", response_model=TaskRunOut)
def reject_task(
    task_id: int,
    data: ApprovalDecision = Body(default=ApprovalDecision()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRun:
    return _run_transition(
        db,
        _task_or_404(db, current_user.id, task_id),
        workflow_service.reject_task,
        data.comment,
    )


@router.get("/{task_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list:
    return _task_or_404(db, current_user.id, task_id).artifacts
