from pydantic import BaseModel, ConfigDict, Field


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=5000)
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedChunkOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int
    filename: str
    chunk_index: int
    content: str
    score: float
