from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=50000)
    model_tier: Literal["auto", "fast", "standard", "reasoning"] = "auto"
