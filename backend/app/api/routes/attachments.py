"""Authenticated private uploads; existing middleware applies RATE_LIMIT_GENERAL."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.attachments import attachment_path, get_attachment, upload_attachment

router = APIRouter()


class AttachmentOut(BaseModel):
    id: int
    type: Literal["image"] = "image"
    mime_type: str
    original_name: str
    url: str
    size_bytes: int
    created_at: datetime


@router.post("", response_model=AttachmentOut, status_code=201)
async def upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttachmentOut:
    attachment = await upload_attachment(db, current_user.id, file)
    path = attachment_path(attachment, current_user.id)
    try:
        result = AttachmentOut(
            id=attachment.id, mime_type=attachment.mime_type,
            original_name=attachment.original_name,
            url=f"/api/chat/attachments/{attachment.id}",
            size_bytes=attachment.size_bytes, created_at=attachment.created_at,
        )
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return result


@router.get("/{attachment_id}")
def download(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    attachment = get_attachment(db, current_user.id, attachment_id)
    return FileResponse(
        attachment_path(attachment, current_user.id),
        media_type=attachment.mime_type, filename=attachment.original_name,
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )