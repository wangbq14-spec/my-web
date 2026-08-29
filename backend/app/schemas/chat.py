from pydantic import BaseModel, ConfigDict, Field

from app.schemas.message import MessageOut


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=50000)
    use_rag: bool = False
    top_k: int = Field(default=5, ge=1, le=20)


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
