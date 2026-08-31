from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="新对话", min_length=1, max_length=200)
    model: str | None = Field(default=None, max_length=100)
    project_id: int | None = None


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    project_id: int | None = None
    pinned: bool = False

    @model_validator(mode="after")
    def validate_title(self) -> "ConversationUpdate":
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("标题不能为空")
        return self


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    model: str | None
    project_id: int | None
    pinned: bool = False
    created_at: datetime
    updated_at: datetime
