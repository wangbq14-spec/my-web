from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.conversation import ConversationOut
from app.schemas.document import DocumentOut
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import project as project_service

router = APIRouter()


def _project_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")


def _validation_error(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectOut:
    try:
        project = project_service.create_project(db, current_user, data)
        db.commit()
        db.refresh(project)
    except ValueError as exc:
        db.rollback()
        raise _validation_error(str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="项目创建失败"
        ) from exc
    return project_service.to_project_out(project)


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectOut]:
    return project_service.list_projects(db, current_user)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectOut:
    project = project_service.get_project(db, current_user, project_id)
    if project is None:
        raise _project_not_found()
    return project_service.to_project_out(project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectOut:
    if not data.model_fields_set:
        raise _validation_error("至少提供一个要更新的字段")
    project = project_service.get_project(db, current_user, project_id)
    if project is None:
        raise _project_not_found()
    try:
        project_service.update_project(db, project, data)
        db.commit()
        db.refresh(project)
    except ValueError as exc:
        db.rollback()
        raise _validation_error(str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="项目更新失败"
        ) from exc
    return project_service.to_project_out(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    project = project_service.get_project(db, current_user, project_id)
    if project is None:
        raise _project_not_found()
    try:
        project_service.delete_project(db, project)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="项目删除失败"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/conversations", response_model=list[ConversationOut])
def list_project_conversations(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ConversationOut]:
    if project_service.get_project(db, current_user, project_id) is None:
        raise _project_not_found()
    return project_service.list_project_conversations(db, current_user, project_id)


@router.get("/{project_id}/documents", response_model=list[DocumentOut])
def list_project_documents(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentOut]:
    if project_service.get_project(db, current_user, project_id) is None:
        raise _project_not_found()
    return project_service.list_project_documents(db, current_user, project_id)
