import re
from typing import Protocol


DEFAULT_TITLE = "新对话"
_MIN_TITLE_LENGTH = 3
_TITLE_CONTENT_LENGTH = 30


class _ConversationWithTitle(Protocol):
    title: str


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]*", re.IGNORECASE),
    re.compile(r"\bbearer(?:\s+[^\s,;]+)?", re.IGNORECASE),
    re.compile(r"\btoken\s*=\s*[^\s&]*", re.IGNORECASE),
    re.compile(r"\bapi[ _-]?key(?:\s*[=:]\s*|\s+)?[^\s,;]*", re.IGNORECASE),
    re.compile(r"\bsecret\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
    re.compile(r"\bpassword\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
    re.compile(r"\btoken(?:\s+|[=:]\s*)[^\s,;]+", re.IGNORECASE),
    re.compile(r"\bkey\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
    re.compile(r"\bclient[_-]?secret\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
    re.compile(r"\bcredential\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_-]{24,}\b"),
)


def generate_title(content: str) -> str:
    """Build a short, deterministic, non-sensitive title from user content."""

    normalized = re.sub(r"\s+", " ", content.strip())
    for pattern in _SECRET_PATTERNS:
        normalized = pattern.sub("", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" -:：,，;；")

    if len(normalized) < _MIN_TITLE_LENGTH:
        return DEFAULT_TITLE
    if len(normalized) > _TITLE_CONTENT_LENGTH:
        return f"{normalized[:_TITLE_CONTENT_LENGTH]}…"
    return normalized


def maybe_auto_title(conversation: _ConversationWithTitle, content: str) -> bool:
    """Set the initial conversation title without changing transaction state."""

    if conversation.title != DEFAULT_TITLE:
        return False
    conversation.title = generate_title(content)
    return True
