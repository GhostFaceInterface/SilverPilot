from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


PriceSourceType = Literal["bank", "global"]


class ManualPriceIngestRequest(BaseModel):
    source_type: PriceSourceType
    source: str = Field(min_length=1, max_length=128)
    asset_symbol: str = Field(default="XAG", min_length=1, max_length=32)
    buy_price: Decimal = Field(gt=Decimal("0"))
    sell_price: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=8)
    observed_at: datetime
    payload: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_spread(self) -> "ManualPriceIngestRequest":
        if self.buy_price < self.sell_price:
            raise ValueError("buy_price must be greater than or equal to sell_price")
        return self


class CollectorRunPayload(BaseModel):
    id: int
    collector_name: str
    source: str
    status: str
    records_seen: int
    records_inserted: int
    duplicates: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class PriceSnapshotPayload(BaseModel):
    id: int
    asset_id: int
    source: str
    buy_price: Decimal
    sell_price: Decimal
    mid_price: Decimal
    currency: str
    spread_absolute: Decimal
    spread_percent: Decimal
    observed_at: datetime


class ManualPriceIngestResponse(BaseModel):
    collector_run: CollectorRunPayload
    raw_inserted: bool
    price_snapshot: PriceSnapshotPayload | None


class CollectorRunResultResponse(BaseModel):
    collector_run: CollectorRunPayload
    raw_inserted: bool
    price_snapshot: PriceSnapshotPayload | None = None


class CollectorHealthItem(BaseModel):
    collector_name: str
    source: str
    status: str
    records_seen: int
    records_inserted: int
    duplicates: int
    age_seconds: int | None
    stale: bool
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None


class ExecutionCriticalHealth(BaseModel):
    bank_price: Literal["missing", "fresh", "manual_fallback", "stale"]
    source: str | None
    age_seconds: int | None
    stale: bool
    manual_fallback: bool


class CollectorHealthResponse(BaseModel):
    status: Literal["empty", "healthy", "degraded", "blocked", "stale"]
    execution_critical: ExecutionCriticalHealth
    stale_after_minutes: int
    collectors: list[CollectorHealthItem]


class CollectorQualityItem(BaseModel):
    collector_name: str
    source: str
    runs: int
    successful_runs: int
    failed_runs: int
    records_seen: int
    records_inserted: int
    duplicates: int
    failure_ratio: float
    duplicate_ratio: float
    missing_runs: int
    missing_ratio: float
    latest_status: str
    latest_finished_at: datetime | None


class CollectorQualityResponse(BaseModel):
    status: Literal["empty", "ok", "degraded"]
    window_hours: int
    expected_interval_minutes: int
    expected_runs_per_collector: int
    collectors: list[CollectorQualityItem]
