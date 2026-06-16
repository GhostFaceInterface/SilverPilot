from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    asset_type: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("measurement_units.id"), nullable=True, index=True)
    quote_currency_id: Mapped[int | None] = mapped_column(ForeignKey("currencies.id"), nullable=True, index=True)

    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="asset")
    market_bars: Mapped[list["MarketBar"]] = relationship(back_populates="asset")
    instrument: Mapped["Instrument | None"] = relationship()
    unit: Mapped["MeasurementUnit | None"] = relationship()
    quote_currency: Mapped["Currency | None"] = relationship()

    @property
    def currency(self) -> str:
        if self.symbol == "XAG_TRY":
            return "TRY"
        if self.quote_currency is not None:
            return self.quote_currency.code
        return "USD"


class Currency(Base):
    __tablename__ = "currencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    numeric_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    minor_unit: Mapped[int] = mapped_column(default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MeasurementUnit(Base):
    __tablename__ = "measurement_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    unit_type: Mapped[str] = mapped_column(String(32), index=True)
    to_base_factor: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("1"))
    base_unit_code: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    instrument_type: Mapped[str] = mapped_column(String(32), index=True)
    native_currency_id: Mapped[int | None] = mapped_column(ForeignKey("currencies.id"), nullable=True, index=True)
    native_unit_id: Mapped[int | None] = mapped_column(ForeignKey("measurement_units.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    native_currency: Mapped["Currency | None"] = relationship()
    native_unit: Mapped["MeasurementUnit | None"] = relationship()


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_run_id: Mapped[int | None] = mapped_column(ForeignKey("collector_runs.id"), nullable=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    buy_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    sell_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    mid_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    spread_absolute: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    spread_percent: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[Asset] = relationship(back_populates="price_snapshots")
    collector_run: Mapped["CollectorRun | None"] = relationship()


class MarketBar(Base):
    __tablename__ = "market_bars"
    __table_args__ = (
        UniqueConstraint(
            "asset_id", "source", "timeframe", "bar_start_at", name="uq_market_bars_asset_source_tf_start"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    bar_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bar_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    sample_count: Mapped[int] = mapped_column(default=0)
    first_price_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("price_snapshots.id"), nullable=True)
    last_price_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("price_snapshots.id"), nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), default="ok", index=True)
    bar_builder_version: Mapped[str] = mapped_column(String(64), default="market-bars-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    asset: Mapped[Asset] = relationship(back_populates="market_bars")
    first_price_snapshot: Mapped[PriceSnapshot | None] = relationship(foreign_keys=[first_price_snapshot_id])
    last_price_snapshot: Mapped[PriceSnapshot | None] = relationship(foreign_keys=[last_price_snapshot_id])


class CollectorRun(Base):
    __tablename__ = "collector_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_name: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    records_seen: Mapped[int] = mapped_column(default=0)
    records_inserted: Mapped[int] = mapped_column(default=0)
    duplicates: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)


class RuntimeHeartbeat(Base):
    __tablename__ = "runtime_heartbeats"
    __table_args__ = (UniqueConstraint("component", name="uq_runtime_heartbeats_component"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    component: Mapped[str] = mapped_column(String(64), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expected_next_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ok", index=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )


class SourceProfile(Base):
    __tablename__ = "source_profiles"
    __table_args__ = (UniqueConstraint("source_key", name="uq_source_profiles_source_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(64), index=True)
    priority: Mapped[int] = mapped_column(default=100, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    stale_after_minutes: Mapped[int] = mapped_column(default=60)
    market_calendar: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reliability_weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("1.0000"))
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )


class StrategyPolicy(Base):
    __tablename__ = "strategy_policies"
    __table_args__ = (UniqueConstraint("strategy_name", name="uq_strategy_policies_strategy_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), default="diagnostic", index=True)
    timeframe_roles: Mapped[dict] = mapped_column(JSON, default=dict)
    freshness_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    min_history: Mapped[dict] = mapped_column(JSON, default=dict)
    notification_policy: Mapped[dict] = mapped_column(JSON, default=dict)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )


class TradingDecisionRun(Base):
    __tablename__ = "trading_decision_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    trigger_collector_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("collector_runs.id"), nullable=True, index=True
    )
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(32), index=True)
    strategy_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    asset_symbol: Mapped[str] = mapped_column(String(32), index=True)
    source_health_json: Mapped[dict] = mapped_column(JSON, default=dict)
    indicator_readiness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    execution_result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    notification_result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )

    trigger_collector_run: Mapped["CollectorRun | None"] = relationship()
    signal: Mapped["Signal | None"] = relationship()


class RawBankPrice(Base):
    __tablename__ = "raw_bank_prices"
    __table_args__ = (
        UniqueConstraint("asset_id", "source", "observed_at", name="uq_raw_bank_prices_asset_source_observed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_run_id: Mapped[int] = mapped_column(ForeignKey("collector_runs.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    buy_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    sell_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[Asset] = relationship()
    collector_run: Mapped[CollectorRun] = relationship()


class RawGlobalPrice(Base):
    __tablename__ = "raw_global_prices"
    __table_args__ = (
        UniqueConstraint("asset_id", "source", "observed_at", name="uq_raw_global_prices_asset_source_observed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_run_id: Mapped[int] = mapped_column(ForeignKey("collector_runs.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    buy_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    sell_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(8))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped[Asset] = relationship()
    collector_run: Mapped[CollectorRun] = relationship()


class RawFxRate(Base):
    __tablename__ = "raw_fx_rates"
    __table_args__ = (
        UniqueConstraint(
            "source", "base_currency", "quote_currency", "observed_at", name="uq_raw_fx_source_pair_observed"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_run_id: Mapped[int] = mapped_column(ForeignKey("collector_runs.id"), index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    base_currency: Mapped[str] = mapped_column(String(8))
    quote_currency: Mapped[str] = mapped_column(String(8))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    collector_run: Mapped[CollectorRun] = relationship()


class RawNews(Base):
    __tablename__ = "raw_news"
    __table_args__ = (UniqueConstraint("source", "url", name="uq_raw_news_source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_run_id: Mapped[int] = mapped_column(ForeignKey("collector_runs.id"), index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    collector_run: Mapped[CollectorRun] = relationship()


class RawEvent(Base):
    __tablename__ = "raw_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    collector_run_id: Mapped[int | None] = mapped_column(ForeignKey("collector_runs.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    raw_payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    collector_run: Mapped[CollectorRun | None] = relationship()


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    is_real_money: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    trades: Mapped[list["PaperTrade"]] = relationship(back_populates="portfolio")
    snapshots: Mapped[list["PortfolioSnapshot"]] = relationship(back_populates="portfolio")


class RiskRule(Base):
    __tablename__ = "risk_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    params_json: Mapped[dict] = mapped_column(JSON, default=dict)


class RiskDecision(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    reason_code: Mapped[str] = mapped_column(String(64), index=True)
    risk_level: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MLInferenceAudit(Base):
    __tablename__ = "ml_inference_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    risk_decision_id: Mapped[int | None] = mapped_column(ForeignKey("risk_decisions.id"), nullable=True, index=True)
    model_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    model_status: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    model_target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_mode: Mapped[str] = mapped_column(String(32), index=True)
    recommendation: Mapped[str] = mapped_column(String(64), index=True)
    predicted_probability: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    feature_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    asset: Mapped[Asset] = relationship()
    risk_decision: Mapped[RiskDecision | None] = relationship()


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    trade_intent_id: Mapped[int | None] = mapped_column(ForeignKey("trade_intents.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    taxes: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    spread_impact: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    cost_breakdown_json: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_decision_id: Mapped[int | None] = mapped_column(ForeignKey("risk_decisions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    portfolio: Mapped[Portfolio] = relationship(back_populates="trades")
    asset: Mapped[Asset] = relationship()
    trade_intent: Mapped["TradeIntentRecord | None"] = relationship()
    risk_decision: Mapped[RiskDecision | None] = relationship()


class ProviderAccount(Base):
    __tablename__ = "provider_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_id", "account_key", name="uq_provider_accounts_tenant_provider_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), index=True)
    portfolio_id: Mapped[int | None] = mapped_column(ForeignKey("portfolios.id"), nullable=True, index=True)
    account_key: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    account_type: Mapped[str] = mapped_column(String(32), default="paper", index=True)
    base_currency_id: Mapped[int | None] = mapped_column(ForeignKey("currencies.id"), nullable=True, index=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    provider: Mapped["Provider"] = relationship()
    portfolio: Mapped["Portfolio | None"] = relationship()
    base_currency: Mapped["Currency | None"] = relationship()


class TradeIntentRecord(Base):
    __tablename__ = "trade_intents"

    id: Mapped[int] = mapped_column(primary_key=True)
    trading_decision_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("trading_decision_runs.id"), nullable=True, index=True
    )
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True, index=True)
    portfolio_id: Mapped[int | None] = mapped_column(ForeignKey("portfolios.id"), nullable=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0"))
    reason_code: Mapped[str] = mapped_column(String(64), index=True)
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    take_profit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    expected_exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    risk_decision_id: Mapped[int | None] = mapped_column(ForeignKey("risk_decisions.id"), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )

    signal: Mapped["Signal | None"] = relationship()
    trading_decision_run: Mapped["TradingDecisionRun | None"] = relationship()
    portfolio: Mapped["Portfolio | None"] = relationship()
    asset: Mapped["Asset | None"] = relationship()
    risk_decision: Mapped["RiskDecision | None"] = relationship()


class AccountLedgerEntry(Base):
    __tablename__ = "account_ledger_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("provider_accounts.id"), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("measurement_units.id"), nullable=True, index=True)
    currency_id: Mapped[int | None] = mapped_column(ForeignKey("currencies.id"), nullable=True, index=True)
    quote_currency_id: Mapped[int | None] = mapped_column(ForeignKey("currencies.id"), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(32), index=True)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    cash_delta: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    taxes: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    paper_trade_id: Mapped[int | None] = mapped_column(ForeignKey("paper_trades.id"), nullable=True, index=True)
    trade_intent_id: Mapped[int | None] = mapped_column(ForeignKey("trade_intents.id"), nullable=True, index=True)
    risk_decision_id: Mapped[int | None] = mapped_column(ForeignKey("risk_decisions.id"), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    account: Mapped["ProviderAccount"] = relationship()
    asset: Mapped["Asset | None"] = relationship()
    instrument: Mapped["Instrument | None"] = relationship()
    unit: Mapped["MeasurementUnit | None"] = relationship()
    currency: Mapped["Currency | None"] = relationship(foreign_keys=[currency_id])
    quote_currency: Mapped["Currency | None"] = relationship(foreign_keys=[quote_currency_id])
    paper_trade: Mapped["PaperTrade | None"] = relationship()
    trade_intent: Mapped["TradeIntentRecord | None"] = relationship()
    risk_decision: Mapped["RiskDecision | None"] = relationship()


class AccountHoldingSnapshot(Base):
    __tablename__ = "account_holding_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "asset_id",
            "instrument_id",
            "unit_id",
            "currency_id",
            name="uq_account_holding_snapshot_dimension",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("provider_accounts.id"), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"), nullable=True, index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("measurement_units.id"), nullable=True, index=True)
    currency_id: Mapped[int | None] = mapped_column(ForeignKey("currencies.id"), nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    source_ledger_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_ledger_entries.id"), nullable=True, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    account: Mapped["ProviderAccount"] = relationship()
    asset: Mapped["Asset | None"] = relationship()
    instrument: Mapped["Instrument | None"] = relationship()
    unit: Mapped["MeasurementUnit | None"] = relationship()
    currency: Mapped["Currency | None"] = relationship()
    source_ledger_entry: Mapped["AccountLedgerEntry | None"] = relationship()


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    price_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("price_snapshots.id"), nullable=True, index=True)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    asset_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    portfolio: Mapped[Portfolio] = relationship(back_populates="snapshots")
    price_snapshot: Mapped[PriceSnapshot | None] = relationship()


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    price_snapshot_id: Mapped[int] = mapped_column(ForeignKey("price_snapshots.id"), nullable=False, index=True)
    indicator_id: Mapped[int | None] = mapped_column(ForeignKey("technical_indicators.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    price_usd_oz: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    price_snapshot: Mapped["PriceSnapshot"] = relationship()
    technical_indicator: Mapped["TechnicalIndicator | None"] = relationship()


class NotificationAudit(Base):
    __tablename__ = "notification_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("signals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    asset_symbol: Mapped[str] = mapped_column(String(32), index=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    notification_action: Mapped[str] = mapped_column(String(32), index=True)
    reason_code: Mapped[str] = mapped_column(String(64), index=True)
    sent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    skipped_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cooldown_seconds: Mapped[int] = mapped_column(default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    signal: Mapped["Signal | None"] = relationship()


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(64), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(128), index=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_estimate: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TechnicalIndicator(Base):
    __tablename__ = "technical_indicators"
    __table_args__ = (
        UniqueConstraint("price_snapshot_id", "timeframe", name="uq_technical_indicators_snapshot_timeframe"),
        UniqueConstraint("market_bar_id", "calculation_version", name="uq_technical_indicators_bar_calc_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    price_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("price_snapshots.id"), nullable=True, index=True)
    market_bar_id: Mapped[int | None] = mapped_column(ForeignKey("market_bars.id"), nullable=True, index=True)
    bar_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    calculation_version: Mapped[str] = mapped_column(String(64), default="technical-indicators-v2", index=True)
    input_bar_count: Mapped[int] = mapped_column(default=0)
    quality_status: Mapped[str] = mapped_column(String(32), default="ok", index=True)
    close_usd_oz: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    rsi_14: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    macd_line: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    macd_signal: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    macd_histogram: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    bb_upper_20_2: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    bb_middle_20_2: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    bb_lower_20_2: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    sma_20: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    sma_50: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    sma_200: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ema_20: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ema_50: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ema_200: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    adx_14: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    plus_di_14: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    minus_di_14: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    bb_bandwidth_20_2: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    bb_percent_b_20_2: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    atr_percent_14: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    rsi_slope_1: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    macd_histogram_slope_1: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    atr_14: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    xau_xag_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    price_snapshot: Mapped[PriceSnapshot | None] = relationship()
    market_bar: Mapped[MarketBar | None] = relationship()


class IndicatorDefinition(Base):
    __tablename__ = "indicator_definitions"
    __table_args__ = (UniqueConstraint("code", "calculation_version", name="uq_indicator_definitions_code_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    value_type: Mapped[str] = mapped_column(String(32), default="decimal")
    calculation_version: Mapped[str] = mapped_column(String(64), default="technical-indicators-v2", index=True)
    params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class TechnicalIndicatorValue(Base):
    __tablename__ = "technical_indicator_values"
    __table_args__ = (
        UniqueConstraint(
            "technical_indicator_id",
            "indicator_definition_id",
            name="uq_technical_indicator_values_indicator_definition",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    technical_indicator_id: Mapped[int] = mapped_column(ForeignKey("technical_indicators.id"), index=True)
    indicator_definition_id: Mapped[int] = mapped_column(ForeignKey("indicator_definitions.id"), index=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_status: Mapped[str] = mapped_column(String(32), default="ok", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    technical_indicator: Mapped["TechnicalIndicator"] = relationship()
    indicator_definition: Mapped["IndicatorDefinition"] = relationship()


class LLMCallTrace(Base):
    __tablename__ = "llm_call_traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(100), index=True)
    model_name: Mapped[str] = mapped_column(String(100), index=True)
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0.000000"))
    latency_ms: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), index=True)
    prompt_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AgentMemoryEvent(Base):
    __tablename__ = "agent_memory_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(256), index=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class HistoricalAgentCache(Base):
    __tablename__ = "historical_agent_caches"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(128), index=True)  # news-agent, risk-agent
    event_type: Mapped[str] = mapped_column(String(64), index=True)  # news_sentiment, signal_critique
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)  # Eşleşen bar zamanı
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)  # Sentiment/Critique JSON payload
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)


class TenantPortfolio(Base):
    __tablename__ = "tenant_portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    portfolio: Mapped["Portfolio"] = relationship()
    provider: Mapped["Provider"] = relationship()


class StrategyParameter(Base):
    __tablename__ = "strategy_parameters"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "strategy_name", "parameter_key", name="uq_strategy_parameters_tenant_strategy_key"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    parameter_key: Mapped[str] = mapped_column(String(128), index=True)
    parameter_value: Mapped[str] = mapped_column(Text)


class AssetConversion(Base):
    __tablename__ = "asset_conversions"
    __table_args__ = (UniqueConstraint("from_asset_id", "to_asset_id", name="uq_asset_conversions_from_to"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    to_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    conversion_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))

    from_asset: Mapped["Asset"] = relationship(foreign_keys=[from_asset_id])
    to_asset: Mapped["Asset"] = relationship(foreign_keys=[to_asset_id])


class ProviderCostRule(Base):
    __tablename__ = "provider_cost_rules"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "asset_id",
            "asset_type",
            "action",
            "effective_from",
            name="uq_provider_cost_rules_provider_asset_action_effective",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), nullable=True, index=True)
    asset_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), default="*", index=True)
    fee_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    fixed_fee: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    provider: Mapped["Provider"] = relationship()
    asset: Mapped["Asset | None"] = relationship()


Index(
    "ix_price_snapshots_asset_source_observed", PriceSnapshot.asset_id, PriceSnapshot.source, PriceSnapshot.observed_at
)

Index(
    "ix_market_bars_asset_source_tf_start",
    MarketBar.asset_id,
    MarketBar.source,
    MarketBar.timeframe,
    MarketBar.bar_start_at,
)

Index(
    "ix_agent_memory_events_composite",
    AgentMemoryEvent.agent_name,
    AgentMemoryEvent.event_type,
    AgentMemoryEvent.key,
    AgentMemoryEvent.created_at,
)

Index(
    "ix_notification_audits_dedupe",
    NotificationAudit.asset_symbol,
    NotificationAudit.strategy_name,
    NotificationAudit.notification_action,
    NotificationAudit.reason_code,
    NotificationAudit.observed_at,
)

Index(
    "ix_provider_cost_rules_lookup",
    ProviderCostRule.provider_id,
    ProviderCostRule.asset_id,
    ProviderCostRule.asset_type,
    ProviderCostRule.action,
    ProviderCostRule.is_active,
)

Index(
    "ix_account_ledger_entries_account_occurred",
    AccountLedgerEntry.account_id,
    AccountLedgerEntry.occurred_at,
    AccountLedgerEntry.id,
)

Index(
    "ix_account_ledger_entries_asset_dimension",
    AccountLedgerEntry.account_id,
    AccountLedgerEntry.asset_id,
    AccountLedgerEntry.instrument_id,
    AccountLedgerEntry.unit_id,
)

Index(
    "ix_account_holding_snapshots_account_dimension",
    AccountHoldingSnapshot.account_id,
    AccountHoldingSnapshot.asset_id,
    AccountHoldingSnapshot.instrument_id,
    AccountHoldingSnapshot.unit_id,
    AccountHoldingSnapshot.currency_id,
)
