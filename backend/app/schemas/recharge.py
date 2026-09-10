"""Recharge requests are untrusted; services must resolve package pricing."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RechargeRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    package_code: str = Field(min_length=1, max_length=40)
    amount_display: str = Field(min_length=1, max_length=40)
    credits_requested: int = Field(gt=0, le=2147483647, strict=True)
    note: str | None = Field(default=None, max_length=10000)


class RechargeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    username: str | None = None
    package_code: str
    amount_display: str
    amount_cny: Decimal | None
    credits_requested: int
    pricing_snapshot: str | None
    status: Literal["pending", "approved", "rejected", "cancelled"]
    note: str | None
    created_at: datetime
    reviewed_at: datetime | None
    reviewed_by: int | None
