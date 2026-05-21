from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


class SignalBase(BaseModel):
    observed_at: datetime
    price_snapshot_id: int
    indicator_id: int | None = None
    action: Literal["BUY", "SELL", "HOLD"]
    reason_code: str = Field(min_length=1, max_length=64)
    price_usd_oz: Decimal = Field(ge=Decimal("0"))
    details_json: dict = Field(default_factory=dict)


class SignalCreate(SignalBase):
    pass


class SignalResponse(SignalBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
