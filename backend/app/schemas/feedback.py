"""User feedback input and output contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal["bug", "suggestion", "other"]
    path: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=2000)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str | None = None
    type: str
    path: str
    message: str
    status: Literal["new", "reviewed", "closed"]
    created_at: datetime
