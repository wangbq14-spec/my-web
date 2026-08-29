from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    filename: str
    original_filename: str
    content_type: str | None
    file_size: int
    status: str
    error_code: str | None
    error_message: str | None
    retry_count: int
    active_generation: int
    processing_generation: int
    processed_at: datetime | None
    created_at: datetime
    updated_at: datetime
