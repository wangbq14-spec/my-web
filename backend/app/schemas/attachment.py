"""Upload association metadata; ownership and storage paths are server-controlled."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class MessageAttachmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: int | None = Field(default=None, gt=0)
    message_id: int | None = Field(default=None, gt=0)
    type: Literal["image"] = "image"


class MessageAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    conversation_id: int | None
    message_id: int | None
    type: str
    mime_type: str
    original_name: str
    size_bytes: int
    created_at: datetime

    @computed_field
    @property
    def url(self) -> str:
        return f"/api/chat/attachments/{self.id}"
