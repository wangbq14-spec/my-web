"""Private image uploads and atomic association with chat messages."""

import re
from datetime import datetime
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.llm.base import ImagePart, LLMMessage, TextPart
from app.models.beta import MessageAttachment

_MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".png": "image/png", ".webp": "image/webp"}


def sanitize_filename(filename: str | None) -> tuple[str, str]:
    name = filename or ""
    normalized = name.replace("\\", "/")
    windows = PureWindowsPath(name)
    if (not name or ".." in normalized.split("/") or normalized.startswith("/")
            or windows.is_absolute() or windows.drive):
        raise HTTPException(400, "文件名包含不安全路径")
    name = normalized.rsplit("/", 1)[-1]
    suffix = Path(name).suffix.lower()
    if suffix not in _MIMES:
        raise HTTPException(415, "仅支持 JPEG、PNG、WebP 图片")
    stem = re.sub(r'[^\w .-]', "_", Path(name).stem).strip(" .")[:200] or "image"
    return stem + suffix, suffix


def valid_magic(data: bytes, mime: str) -> bool:
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def storage_directory(user_id: int) -> Path:
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise HTTPException(400, "无效用户")
    root = Path(settings.RAG_UPLOAD_DIR).resolve()
    directory = root / "chat_attachments" / str(user_id)
    if not directory.resolve().is_relative_to(root):
        raise HTTPException(400, "无效附件路径")
    return directory


def attachment_path(attachment: MessageAttachment, user_id: int) -> Path:
    if attachment.user_id != user_id or attachment.type != "image":
        raise HTTPException(404, "附件不存在")
    directory = storage_directory(user_id).resolve()
    path = Path(attachment.storage_path)
    # Only a direct UUID-named child of this user's private directory is valid.
    if (not re.fullmatch(r"[0-9a-f]{32}\.(?:jpg|jpeg|png|webp)", path.name)
            or path.is_symlink() or path.resolve().parent != directory):
        raise HTTPException(400, "无效附件路径")
    if not path.is_file():
        raise HTTPException(404, "附件文件不存在，请重新上传")
    if attachment.mime_type not in _MIMES.values():
        raise HTTPException(400, "无效图片格式")
    return path


async def upload_attachment(session: Session, user_id: int, file: UploadFile) -> MessageAttachment:
    try:
        original_name, suffix = sanitize_filename(file.filename)
        mime = _MIMES[suffix]
        if file.content_type != mime:
            raise HTTPException(415, "图片扩展名与 MIME 类型不匹配")
        data = await file.read(settings.MAX_CHAT_IMAGE_SIZE + 1)
        if len(data) > settings.MAX_CHAT_IMAGE_SIZE:
            raise HTTPException(413, "图片超过大小限制")
        if not valid_magic(data, mime):
            raise HTTPException(415, "图片内容与声明格式不匹配")
        directory = storage_directory(user_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (uuid4().hex + suffix)
        # Exclusive creation prevents overwriting even on a UUID collision.
        with path.open("xb") as output:
            output.write(data)
        attachment = MessageAttachment(
            user_id=user_id, type="image", mime_type=mime,
            original_name=original_name, storage_path=str(path),
            size_bytes=len(data),
        )
        try:
            session.add(attachment)
            session.flush()
            session.refresh(attachment)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return attachment
    finally:
        await file.close()


def get_attachment(session: Session, user_id: int, attachment_id: int) -> MessageAttachment:
    attachment = session.scalar(select(MessageAttachment).where(
        MessageAttachment.id == attachment_id, MessageAttachment.user_id == user_id,
        MessageAttachment.type == "image"))
    if attachment is None:
        raise HTTPException(404, "附件不存在")
    return attachment


def cleanup_orphan_attachments(session: Session, before: datetime) -> int:
    """Remove abandoned or orphaned image rows and files.

    Orphans are attachments never bound to a message (``message_id`` IS NULL)
    older than ``before`` — abandoned composer uploads or leftovers from
    deleted messages/conversations (FK ON DELETE SET NULL). Only files inside
    the configured upload root are ever touched. Returns the number removed.
    """
    root = Path(settings.RAG_UPLOAD_DIR).resolve()
    rows = session.scalars(
        select(MessageAttachment).where(
            MessageAttachment.message_id.is_(None),
            MessageAttachment.created_at < before,
        )
    ).all()
    for attachment in rows:
        path = Path(attachment.storage_path)
        try:
            if path.is_file() and path.resolve().is_relative_to(root):
                path.unlink()
        except OSError:
            pass
        session.delete(attachment)
    session.flush()
    return len(rows)


def validate_attachments(session: Session, user_id: int, conversation_id: int,
                         attachment_ids: list[int] | None) -> list[MessageAttachment]:
    ids = attachment_ids or []
    if len(ids) > settings.MAX_CHAT_IMAGES_PER_MESSAGE:
        raise HTTPException(400, "每条消息图片数量超过限制")
    if (len(ids) != len(set(ids))
            or any(type(value) is not int or value <= 0 for value in ids)):
        raise HTTPException(400, "附件 ID 无效或重复")
    attachments = [get_attachment(session, user_id, value) for value in ids]
    for attachment in attachments:
        if attachment.message_id is not None or attachment.conversation_id not in (None, conversation_id):
            raise HTTPException(400, "附件已绑定其他消息或会话")
        attachment_path(attachment, user_id)
    if ids:
        # Serialize binds within one conversation on databases supporting row locks.
        from app.models.conversation import Conversation
        session.execute(select(Conversation.id).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        ).with_for_update()).first()
        existing = session.scalars(select(MessageAttachment.id).where(
            MessageAttachment.conversation_id == conversation_id,
            MessageAttachment.user_id == user_id, MessageAttachment.type == "image")).all()
        if len(set(existing) | set(ids)) > settings.MAX_CHAT_IMAGES_PER_CONVERSATION:
            raise HTTPException(400, "每会话图片数量超过限制")
    return attachments


def bind_attachments(session: Session, user_id: int, conversation_id: int,
                     message_id: int, attachments: list[MessageAttachment]) -> None:
    for attachment in attachments:
        result = session.execute(update(MessageAttachment).where(
            MessageAttachment.id == attachment.id,
            MessageAttachment.user_id == user_id,
            MessageAttachment.message_id.is_(None),
            (MessageAttachment.conversation_id.is_(None)
             | (MessageAttachment.conversation_id == conversation_id)),
        ).values(conversation_id=conversation_id, message_id=message_id))
        if result.rowcount != 1:
            raise HTTPException(409, "附件已被其他消息使用")
    session.flush()


def build_messages(session: Session, user_id: int, history) -> list[LLMMessage]:
    ids = [message.id for message in history]
    attachments = session.scalars(select(MessageAttachment).where(
        MessageAttachment.message_id.in_(ids),
        MessageAttachment.user_id == user_id)).all() if ids else []
    grouped = {}
    conversations = {message.id: message.conversation_id for message in history}
    for attachment in attachments:
        if attachment.conversation_id != conversations[attachment.message_id]:
            raise HTTPException(400, "附件会话不匹配")
        grouped.setdefault(attachment.message_id, []).append(attachment)
    result = []
    for message in history:
        images = sorted(grouped.get(message.id, []), key=lambda item: item.id)
        if len(images) > settings.MAX_CHAT_IMAGES_PER_MESSAGE:
            raise HTTPException(400, "每条消息图片数量超过限制")
        parts = None
        if images:
            # Image-only messages carry no text; never emit an empty TextPart.
            parts = ([TextPart(text=message.content)] if message.content else []) + [
                ImagePart(data_url_or_path=str(attachment_path(image, user_id)),
                          mime_type=image.mime_type) for image in images]
        result.append(LLMMessage(role=message.role, content=message.content, content_parts=parts))
    return result