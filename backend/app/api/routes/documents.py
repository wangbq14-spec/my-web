import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.rag.storage import StorageSecurityError, delete_upload, save_upload
from app.schemas.document import DocumentOut
from app.services import document as document_service
from app.services import project as project_service
from app.services.document_tasks import (
    get_document_task_dispatcher,
    mark_document_task_dispatched,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_SUFFIXES = {".txt", ".md", ".pdf"}
_CONTENT_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
}
_READ_CHUNK_BYTES = 64 * 1024


class DocumentProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int | None


def _log_document_route_event(
    *, event: str, document_id: int | None = None, error_code: str
) -> None:
    """Log only diagnostic identifiers that are safe for production logs."""
    logger.info(
        json.dumps(
            {
                "event": event,
                "service": "documents-api",
                "document_id": document_id,
                "error_code": error_code,
            }
        )
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="\u6587\u6863\u4e0d\u5b58\u5728")


@router.post("", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    file: UploadFile = File(...),
    project_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    original_filename = file.filename or ""
    suffix = Path(original_filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="\u4e0d\u652f\u6301\u7684\u6587\u4ef6\u7c7b\u578b",
        )

    parts: list[bytes] = []
    file_size = 0
    while content := file.file.read(_READ_CHUNK_BYTES):
        file_size += len(content)
        if file_size > settings.RAG_MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="\u6587\u4ef6\u8fc7\u5927",
            )
        parts.append(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="\u6587\u4ef6\u4e3a\u7a7a"
        )

    if project_id is not None and project_service.get_project(
        db, current_user, project_id
    ) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    try:
        filename = save_upload(b"".join(parts), suffix)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="\u6587\u4ef6\u4fdd\u5b58\u5931\u8d25"
        ) from exc

    try:
        document = document_service.create_document(
            db,
            user_id=current_user.id,
            filename=filename,
            original_filename=original_filename,
            content_type=_CONTENT_TYPES[suffix],
            file_size=file_size,
            project_id=project_id,
        )
        if project_id is not None:
            project_service.touch_project_activity(db, project_id)
        db.commit()
    except SQLAlchemyError as exc:
        _log_document_route_event(
            event="document_database_write", error_code="database_write_failed"
        )
        db.rollback()
        try:
            delete_upload(filename)
        except (OSError, StorageSecurityError):
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="\u6587\u6863\u4fdd\u5b58\u5931\u8d25",
        ) from exc

    try:
        get_document_task_dispatcher().enqueue(document.id)
    except Exception:
        # The persisted queued document is the durable source for dispatcher scans.
        _log_document_route_event(
            event="document_task_enqueue",
            document_id=document.id,
            error_code="task_enqueue_failed",
        )
    else:
        try:
            mark_document_task_dispatched(db, document.id)
            db.commit()
            db.refresh(document)
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Document processing could not be accepted.",
            ) from exc
    return document


@router.get("", response_model=list[DocumentOut])
def list_user_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Document]:
    return document_service.list_documents(db, user_id=current_user.id)


@router.get("/{document_id}", response_model=DocumentOut)
def get_user_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    document = document_service.get_document(
        db, user_id=current_user.id, document_id=document_id
    )
    if document is None:
        raise _not_found()
    return document


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document_project(
    document_id: int,
    data: DocumentProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    document = document_service.get_document(
        db, user_id=current_user.id, document_id=document_id
    )
    if document is None:
        raise _not_found()
    if data.project_id is not None and project_service.get_project(
        db, current_user, data.project_id
    ) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    try:
        document_service.update_document_project(
            db, document=document, project_id=data.project_id
        )
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文档更新失败"
        ) from exc
    return document


@router.post(
    "/{document_id}/retry",
    response_model=DocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_user_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    document = document_service.get_document(
        db, user_id=current_user.id, document_id=document_id
    )
    if document is None:
        raise _not_found()
    if not document_service.reset_for_manual_retry(db, document_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed documents can be retried.",
        )

    try:
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document retry could not be accepted.",
        ) from exc

    try:
        get_document_task_dispatcher().enqueue(document_id)
    except Exception:
        # Keep the durable queued state so a dispatcher scan can re-submit it.
        _log_document_route_event(
            event="document_retry_enqueue",
            document_id=document_id,
            error_code="retry_enqueue_failed",
        )
    else:
        try:
            mark_document_task_dispatched(db, document_id)
            db.commit()
            db.refresh(document)
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Document retry could not be accepted.",
            ) from exc
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    document = document_service.get_document(
        db, user_id=current_user.id, document_id=document_id
    )
    if document is None:
        raise _not_found()

    try:
        if not document_service.soft_delete_document(db, document_id, current_user.id):
            raise _not_found()
        document_service.delete_document_chunks(db, document_id=document_id)
        db.flush()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="\u6587\u6863\u5220\u9664\u5931\u8d25",
        ) from exc

    try:
        delete_upload(document.filename)
    except (OSError, StorageSecurityError) as exc:
        # The soft delete and chunk removal are still uncommitted, so this
        # rollback restores both before reporting the file-system failure.
        db.rollback()
        _log_document_route_event(
            event="document_file_delete",
            document_id=document_id,
            error_code="file_delete_failed",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除失败，请重试",
        ) from exc

    try:
        db.commit()
    except SQLAlchemyError as exc:
        # The database and file system are not atomic. If the file deletion
        # succeeds but this commit fails, rollback retains the document and
        # chunks (including ready/searchable documents). Retrying DELETE
        # completes the deletion because delete_upload is idempotent.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档删除失败",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
