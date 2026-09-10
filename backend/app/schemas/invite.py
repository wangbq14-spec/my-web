"""Invite management input and output contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InviteCodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=64)
    channel: str = Field(min_length=1, max_length=40)
    max_uses: int = Field(gt=0, strict=True)
    is_active: bool = True
    expires_at: datetime | None = None


class InviteCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    channel: str
    max_uses: int
    used_count: int
    is_active: bool
    expires_at: datetime | None
    created_by: int | None
    created_at: datetime
