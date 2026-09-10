from pathlib import Path
from uuid import uuid4

from app.core.config import settings

ALLOWED_SUFFIXES = {".txt", ".md", ".pdf"}


class StorageSecurityError(Exception):
    """Raised when a requested upload path is outside the configured directory."""


def _upload_dir() -> Path:
    return Path(settings.RAG_UPLOAD_DIR).resolve()


def _normalise_suffix(suffix: str) -> str:
    lowered = suffix.lower()
    return lowered if lowered in ALLOWED_SUFFIXES else ""


def save_upload(content: bytes, suffix: str) -> str:
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{_normalise_suffix(suffix)}"
    path = upload_dir / filename
    try:
        path.write_bytes(content)
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return filename


def resolve_upload_path(filename: str) -> Path:
    upload_dir = _upload_dir()
    candidate = (upload_dir / filename).resolve()
    try:
        candidate.relative_to(upload_dir)
    except ValueError as exc:
        raise StorageSecurityError("Invalid upload path") from exc
    return candidate


def delete_upload(filename: str) -> None:
    resolve_upload_path(filename).unlink(missing_ok=True)
