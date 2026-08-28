from pydantic import BaseModel, ConfigDict, Field

from app.schemas.message import MessageOut


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=50000)


class ChatResponse(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
