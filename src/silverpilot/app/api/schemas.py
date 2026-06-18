from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str
    app: str


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class PaginatedResponse(BaseModel, Generic[T]):  # noqa: UP046
    items: list[T]
    meta: PageMeta


class WalletResponse(BaseModel):
    id: UUID
    account_id: UUID
    currency_id: UUID
    currency_code: str
    available_amount: Decimal
    reserved_amount: Decimal
    created_at: datetime


class AccountResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    base_currency_id: UUID
    base_currency_code: str
    execution_venue_id: UUID
    execution_venue_code: str
    starting_balance: Decimal
    status: str
    created_at: datetime


class BankResponse(BaseModel):
    id: UUID
    code: str
    name: str
    country_code: str
    status: str
    source_policy: str | None
    created_at: datetime


class ExecutionInstrumentResponse(BaseModel):
    id: UUID
    execution_venue_id: UUID
    execution_venue_code: str
    bank_instrument_id: UUID | None
    symbol: str
    metal_code: str
    currency_code: str
    unit_code: str
    status: str
    created_at: datetime


class PriceQuoteResponse(BaseModel):
    id: UUID
    bank_instrument_id: UUID
    bank_buy_price: Decimal
    bank_sell_price: Decimal
    observed_at: datetime
    fetched_at: datetime
    source: str
    freshness_status: str


class IndicatorSnapshotResponse(BaseModel):
    id: UUID
    instrument_type: str
    instrument_id: UUID
    source: str
    timeframe: str
    indicator_name: str
    parameters: dict[str, Any]
    value: Decimal
    calculated_at: datetime
    source_bar_end_at: datetime


class MarketRegimeSnapshotResponse(BaseModel):
    id: UUID
    instrument_type: str
    instrument_id: UUID
    source: str
    timeframe: str
    regime: str
    confidence: Decimal
    evidence: dict[str, Any]
    config_version: str
    starts_at: datetime
    confirmed_at: datetime
    source_bar_end_at: datetime


class PaperTradeResponse(BaseModel):
    id: UUID
    order_id: UUID
    account_id: UUID
    execution_instrument_id: UUID
    bank_instrument_id: UUID
    quote_id: UUID
    side: str
    quantity: Decimal
    execution_price: Decimal
    gross_cash_amount: Decimal
    fees: Decimal
    taxes: Decimal
    spread_cost: Decimal
    net_cash_amount: Decimal
    realized_pnl: Decimal
    executed_at: datetime


class PositionResponse(BaseModel):
    id: UUID
    account_id: UUID
    bank_instrument_id: UUID
    quantity: Decimal
    average_cost: Decimal
    realized_pnl: Decimal
    created_at: datetime


class BacktestRunSummaryResponse(BaseModel):
    id: UUID
    dataset_snapshot_id: UUID
    account_id: UUID
    strategy_id: UUID
    config_hash: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    pnl_after_costs: Decimal | None = None
    trade_count: int | None = None
    max_drawdown: Decimal | None = None


class BacktestRunResponse(BacktestRunSummaryResponse):
    report: dict[str, Any] = Field(default_factory=dict)


class PositionValuationResponse(BaseModel):
    position_id: UUID
    bank_instrument_id: UUID
    quantity: Decimal
    average_cost: Decimal
    latest_bank_buy_price: Decimal | None
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    valuation_status: str


class PortfolioReportResponse(BaseModel):
    account_id: UUID
    captured_at: datetime
    base_currency_code: str
    cash_available: Decimal
    cash_reserved: Decimal
    positions_market_value: Decimal
    total_value: Decimal
    starting_balance: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    net_pnl: Decimal
    return_pct: Decimal | None
    indicative_pricing_note: str
    positions: list[PositionValuationResponse]


class PnlReportResponse(BaseModel):
    account_id: UUID
    gross_trade_cash: Decimal
    fees: Decimal
    taxes: Decimal
    spread_cost: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    net_pnl: Decimal
    trade_count: int


class RiskReportResponse(BaseModel):
    account_id: UUID
    pending_intent_count: int
    approved_decision_count: int
    reduced_decision_count: int
    rejected_decision_count: int
    latest_decision_at: datetime | None
    rejection_reasons: dict[str, int]


class AccountHealthReportResponse(BaseModel):
    account_id: UUID
    account_status: str
    wallet_count: int
    open_position_count: int
    stale_position_price_count: int
    latest_quote_at: datetime | None
    latest_trade_at: datetime | None
    latest_risk_decision_at: datetime | None
    status: str


class AccountDashboardReportResponse(BaseModel):
    account: AccountResponse
    portfolio: PortfolioReportResponse
    pnl: PnlReportResponse
    risk: RiskReportResponse
    health: AccountHealthReportResponse


class ReportResponse(BaseModel):
    id: UUID
    report_type: str
    payload: dict[str, Any]
