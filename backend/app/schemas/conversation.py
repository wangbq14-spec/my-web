from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="新对话", min_length=1, max_length=200)
    model: str | None = Field(default=None, max_length=100)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    model: str | None
    created_at: datetime
    updated_at: datetime
