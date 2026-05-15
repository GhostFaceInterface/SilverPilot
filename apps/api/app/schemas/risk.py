from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class RiskThresholdsPayload(BaseModel):
    data_stale_after_minutes: int
    max_spread_percent: Decimal
    max_24h_volatility_percent: Decimal
    max_7d_volatility_percent: Decimal
    fomo_lookback_minutes: int
    fomo_rise_percent: Decimal
    max_daily_loss_usd: Decimal
    max_weekly_loss_usd: Decimal
    min_expected_net_gain_percent: Decimal


class RiskCurrentMetricsPayload(BaseModel):
    global_xag_volatility_24h_percent: Decimal | None
    global_xag_volatility_24h_source: str | None
    global_xag_volatility_24h_sample_count: int | None
    global_xag_volatility_7d_percent: Decimal | None
    global_xag_volatility_7d_source: str | None
    global_xag_volatility_7d_sample_count: int | None
    fomo_rise_percent: Decimal | None
    fomo_rise_source: str | None
    fomo_rise_sample_count: int | None
    daily_realized_loss_usd: Decimal
    weekly_realized_loss_usd: Decimal


class RiskWouldBlockPayload(BaseModel):
    reason_code: str
    risk_level: str
    metric: str
    threshold: str
    window_hours: int | None = None
    lookback_minutes: int | None = None
    source: str | None = None
    sample_count: int | None = None


class RiskThresholdHeadroomPayload(BaseModel):
    metric_name: str
    reason_code: str
    risk_level: str
    metric: str | None
    threshold: str
    remaining_to_block: str | None
    used_percent: str | None
    status: str
    window_hours: int | None = None
    lookback_minutes: int | None = None
    source: str | None = None
    sample_count: int | None = None


class RecentRiskDecisionCountPayload(BaseModel):
    decision: str
    reason_code: str
    count: int


class GlobalXagSourceDiagnosticsPayload(BaseModel):
    source: str
    sample_count: int
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    min_price: Decimal | None
    max_price: Decimal | None
    range_percent: Decimal | None


class GlobalXagWindowDiagnosticsPayload(BaseModel):
    window_hours: int
    sample_count: int
    first_observed_at: datetime | None
    last_observed_at: datetime | None
    latest_source: str | None
    latest_price: Decimal | None
    min_price: Decimal | None
    max_price: Decimal | None
    range_percent: Decimal | None
    sources: list[GlobalXagSourceDiagnosticsPayload]


class RiskPolicyStatusResponse(BaseModel):
    portfolio_name: str
    asset_symbol: str
    thresholds: RiskThresholdsPayload
    current_metrics: RiskCurrentMetricsPayload
    would_block_now: list[RiskWouldBlockPayload]
    threshold_headroom: list[RiskThresholdHeadroomPayload]
    recent_decisions: list[RecentRiskDecisionCountPayload]
    global_xag_diagnostics: list[GlobalXagWindowDiagnosticsPayload]
