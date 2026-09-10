from datetime import datetime
from pydantic import BaseModel, ConfigDict
class BalanceOut(BaseModel):
    balance: int
    updated_at: datetime
class UsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    provider: str; model: str; model_tier: str | None
    prompt_tokens: int; completion_tokens: int; total_tokens: int
    estimated_cost: float; credits_charged: int; status: str; created_at: datetime
    kind: str | None = None
