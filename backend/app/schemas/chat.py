from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.message import MessageOut


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(max_length=50000)
    model_tier: Literal["auto", "fast", "standard", "reasoning"] = "auto"
    attachment_ids: list[int] = Field(default_factory=list)
    use_rag: bool = False
    top_k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def _require_text_or_attachment(self) -> "ChatRequest":
        # A multimodal message is valid with text, attachments, or both; only a
        # completely empty message is rejected.
        if not self.content.strip() and not self.attachment_ids:
            raise ValueError("请输入内容或添加图片。")
        return self


class CitationOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    document_id: int
    filename: str
    chunk_index: int
    score: float
    excerpt: str


class ChatResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    sources: list[CitationOut] = []
