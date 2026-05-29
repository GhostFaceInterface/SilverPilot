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

    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="asset")

    @property
    def currency(self) -> str:
        if self.symbol == "XAG_GRAM":
            return "TRY"
        return "USD"


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
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


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    taxes: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    risk_decision_id: Mapped[int | None] = mapped_column(ForeignKey("risk_decisions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    portfolio: Mapped[Portfolio] = relationship(back_populates="trades")
    asset: Mapped[Asset] = relationship()
    risk_decision: Mapped[RiskDecision | None] = relationship()


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), index=True)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    asset_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    portfolio: Mapped[Portfolio] = relationship(back_populates="snapshots")


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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    price_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("price_snapshots.id"), nullable=True, index=True)
    bar_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
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
    atr_14: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    xau_xag_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    price_snapshot: Mapped[PriceSnapshot | None] = relationship()


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


Index(
    "ix_price_snapshots_asset_source_observed", PriceSnapshot.asset_id, PriceSnapshot.source, PriceSnapshot.observed_at
)

Index(
    "ix_agent_memory_events_composite",
    AgentMemoryEvent.agent_name,
    AgentMemoryEvent.event_type,
    AgentMemoryEvent.key,
    AgentMemoryEvent.created_at,
)
