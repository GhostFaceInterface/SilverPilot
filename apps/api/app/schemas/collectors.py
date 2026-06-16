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
    collector_run_id: int | None = None
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
    duplicate_without_new_price: bool = False
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
    global_xag_usd: Literal["missing", "fresh", "manual_fallback", "stale"]
    global_xag_source: str | None
    selected_global_xag_source: str | None
    global_xag_age_seconds: int | None
    global_xag_stale: bool
    global_xag_manual_fallback: bool
    usd_try: Literal["missing", "fresh", "stale"]
    usd_try_source: str | None
    usd_try_age_seconds: int | None
    usd_try_stale: bool


class CollectorHealthResponse(BaseModel):
    status: Literal["empty", "healthy", "degraded", "blocked", "stale"]
    execution_critical_status: Literal["healthy", "degraded", "blocked", "stale"]
    context_status: Literal["empty", "healthy", "degraded"]
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
    window_started_at: datetime | None
    elapsed_minutes: int
    validation_window_complete: bool
    expected_interval_minutes: int
    expected_runs_per_collector: int
    expected_runs_so_far_per_collector: int
    collectors: list[CollectorQualityItem]


class CollectorValidationGateResponse(BaseModel):
    status: Literal["empty", "warming_up", "ready", "degraded", "blocked"]
    phase4_allowed: bool
    reasons: list[str]
    blocking_reasons: list[str]
    degraded_reasons: list[str]
    health_status: Literal["empty", "healthy", "degraded", "blocked", "stale"]
    quality_status: Literal["empty", "ok", "degraded"]
    execution_critical_status: Literal["healthy", "degraded", "blocked", "stale"]
    context_status: Literal["empty", "healthy", "degraded"]
    source_reliability: list[dict]
    stooq_xag_usd_timeout_count: int
    provider_failure_counts: dict[str, int]
    selected_global_xag_source: str | None
    window_hours: int
    elapsed_minutes: int
    validation_window_complete: bool
    expected_interval_minutes: int
    expected_runs_per_collector: int
    expected_runs_so_far_per_collector: int
