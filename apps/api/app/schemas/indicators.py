from datetime import datetime

from pydantic import BaseModel


class IndicatorReadinessResponse(BaseModel):
    asset_symbol: str
    timeframe: str
    status: str
    usable: bool
    reason_codes: list[str]
    required_min_bar_count: int
    required_fields: list[str]
    indicator_id: int | None
    market_bar_id: int | None
    price_snapshot_id: int | None
    source: str | None
    bar_timestamp: datetime | None
    age_seconds: int | None
    freshness_minutes: int
    calculation_version: str | None
    quality_status: str | None
    input_bar_count: int | None
    missing_required_fields: list[str]
    close_usd_oz: float | None
    timeframe_policy: dict[str, str] | None = None
    policy_readiness: list["IndicatorReadinessPolicyFrame"] | None = None


class IndicatorReadinessPolicyFrame(BaseModel):
    role: str
    timeframe: str
    max_age_minutes: int
    readiness: IndicatorReadinessResponse
