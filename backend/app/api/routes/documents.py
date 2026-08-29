from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)
from app.api.routes.auth import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.rag import processing
from app.rag.embeddings.base import EmbeddingError
from app.rag.processing import process_document
from app.rag.parsers.base import ParserError
from app.rag.storage import StorageSecurityError, delete_upload, save_upload
from app.schemas.document import DocumentOut
from app.services import document as document_service

router = APIRouter()

_ALLOWED_SUFFIXES = {".txt", ".md", ".pdf"}
_CONTENT_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
}
_READ_CHUNK_BYTES = 64 * 1024


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")


def _processing_error_message(error: Exception) -> str:
    if isinstance(error, ParserError):
        return "文档解析失败"
    if isinstance(error, EmbeddingError):
        return "Embedding 服务不可用"
    return "文档处理失败"


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    original_filename = file.filename or ""
    suffix = Path(original_filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="不支持的文件类型",
        )

    parts: list[bytes] = []
    file_size = 0
    while content := file.file.read(_READ_CHUNK_BYTES):
        file_size += len(content)
        if file_size > settings.RAG_MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="文件过大",
            )
        parts.append(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="文件为空"
        )

    content = b"".join(parts)
    try:
        filename = save_upload(content, suffix)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件保存失败"
        ) from exc

    try:
        document = document_service.create_document(
            db,
            user_id=current_user.id,
            filename=filename,
            original_filename=original_filename,
            content_type=_CONTENT_TYPES[suffix],
            file_size=file_size,
        )
        db.commit()
    except SQLAlchemyError as exc:
        logger.exception("Document 写入 MySQL 失败，filename=%s", filename)
        db.rollback()
        try:
            delete_upload(filename)
        except (OSError, StorageSecurityError):
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文档保存失败"
        ) from exc

    document_id = document.id
    try:
        process_document(db, current_user.id, document)
        db.commit()
    except Exception as exc:
        db.rollback()
        # The vector store is in-memory and deletion is idempotent. This also
        # compensates for a DB commit failure after a successful upsert.
        try:
            processing.get_vector_store().delete_document(current_user.id, document_id)
        except Exception:
            pass
        failed_document = document_service.get_document(
            db, user_id=current_user.id, document_id=document_id
        )
        if failed_document is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文档处理失败"
            ) from exc
        failed_document.status = "failed"
        failed_document.error_message = _processing_error_message(exc)
        try:
            db.commit()
        except SQLAlchemyError as commit_error:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文档处理失败"
            ) from commit_error
        return failed_document

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


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    try:
        document = document_service.delete_document(
            db, user_id=current_user.id, document_id=document_id
        )
        if document is None:
            raise _not_found()
        delete_upload(document.filename)
        processing.get_vector_store().delete_document(current_user.id, document_id)
        db.commit()
    except HTTPException:
        raise
    except (OSError, StorageSecurityError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文件删除失败"
        ) from exc
    except (SQLAlchemyError, Exception) as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="文档删除失败"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
