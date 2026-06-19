from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from silverpilot.app.db.base import Base


def uuid_pk() -> Mapped[UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)


def utc_datetime() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CurrencyModel(Base, TimestampMixin):
    __tablename__ = "currencies"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(3), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    decimal_places: Mapped[int] = mapped_column(nullable=False)

    __table_args__ = (
        CheckConstraint("decimal_places >= 0 AND decimal_places <= 8", name="decimal_places_range"),
    )


class MetalModel(Base, TimestampMixin):
    __tablename__ = "metals"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    default_unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)

    default_unit: Mapped["UnitModel"] = relationship(back_populates="default_for_metals")


class UnitModel(Base, TimestampMixin):
    __tablename__ = "units"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    precision: Mapped[int] = mapped_column(nullable=False)

    default_for_metals: Mapped[list[MetalModel]] = relationship(back_populates="default_unit")

    __table_args__ = (
        CheckConstraint("precision >= 0 AND precision <= 12", name="precision_range"),
    )


class UnitConversionRuleModel(Base, TimestampMixin):
    __tablename__ = "unit_conversion_rules"

    id: Mapped[UUID] = uuid_pk()
    from_unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    to_unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    factor: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    effective_from: Mapped[datetime] = utc_datetime()
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    from_unit: Mapped[UnitModel] = relationship(foreign_keys=[from_unit_id])
    to_unit: Mapped[UnitModel] = relationship(foreign_keys=[to_unit_id])

    __table_args__ = (
        CheckConstraint("factor > 0", name="factor_positive"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="effective_window_valid",
        ),
        Index(
            "ix_unit_conversion_rules_units_effective",
            "from_unit_id",
            "to_unit_id",
            "effective_from",
        ),
    )


class UserModel(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = uuid_pk()
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, unique=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    virtual_accounts: Mapped[list["VirtualAccountModel"]] = relationship(back_populates="user")

    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR external_id IS NOT NULL", name="identity_required"),
        Index("ix_users_status", "status"),
    )


class BankModel(Base, TimestampMixin):
    __tablename__ = "banks"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    source_policy: Mapped[str | None] = mapped_column(String(500), nullable=True)

    execution_venues: Mapped[list["ExecutionVenueModel"]] = relationship(back_populates="bank")

    __table_args__ = (Index("ix_banks_status", "status"),)


class ExecutionVenueModel(Base, TimestampMixin):
    __tablename__ = "execution_venues"

    id: Mapped[UUID] = uuid_pk()
    venue_type: Mapped[str] = mapped_column(String(32), nullable=False)
    bank_id: Mapped[UUID | None] = mapped_column(ForeignKey("banks.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    bank: Mapped[BankModel | None] = relationship(back_populates="execution_venues")
    execution_instruments: Mapped[list["ExecutionInstrumentModel"]] = relationship(
        back_populates="execution_venue"
    )

    __table_args__ = (Index("ix_execution_venues_type_status", "venue_type", "status"),)


class BankInstrumentModel(Base, TimestampMixin):
    __tablename__ = "bank_instruments"

    id: Mapped[UUID] = uuid_pk()
    bank_id: Mapped[UUID] = mapped_column(ForeignKey("banks.id"), nullable=False)
    metal_id: Mapped[UUID] = mapped_column(ForeignKey("metals.id"), nullable=False)
    currency_id: Mapped[UUID] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    min_trade_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    quantity_precision: Mapped[int] = mapped_column(nullable=False)
    price_precision: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    bank: Mapped[BankModel] = relationship()
    metal: Mapped[MetalModel] = relationship()
    currency: Mapped[CurrencyModel] = relationship()
    unit: Mapped[UnitModel] = relationship()

    __table_args__ = (
        UniqueConstraint("bank_id", "metal_id", "currency_id", "unit_id"),
        CheckConstraint("min_trade_amount >= 0", name="min_trade_amount_non_negative"),
        CheckConstraint(
            "quantity_precision >= 0 AND quantity_precision <= 12", name="quantity_precision_range"
        ),
        CheckConstraint(
            "price_precision >= 0 AND price_precision <= 8", name="price_precision_range"
        ),
    )


class ExecutionInstrumentModel(Base, TimestampMixin):
    __tablename__ = "execution_instruments"

    id: Mapped[UUID] = uuid_pk()
    execution_venue_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_venues.id"), nullable=False
    )
    bank_instrument_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bank_instruments.id"), nullable=True
    )
    metal_id: Mapped[UUID] = mapped_column(ForeignKey("metals.id"), nullable=False)
    currency_id: Mapped[UUID] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    execution_venue: Mapped[ExecutionVenueModel] = relationship(
        back_populates="execution_instruments"
    )
    bank_instrument: Mapped[BankInstrumentModel | None] = relationship()
    metal: Mapped[MetalModel] = relationship()
    currency: Mapped[CurrencyModel] = relationship()
    unit: Mapped[UnitModel] = relationship()

    __table_args__ = (
        UniqueConstraint("execution_venue_id", "metal_id", "currency_id", "unit_id"),
        Index("ix_execution_instruments_status", "status"),
    )


class ReferenceMarketInstrumentModel(Base, TimestampMixin):
    __tablename__ = "reference_market_instruments"

    id: Mapped[UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    metal_id: Mapped[UUID] = mapped_column(ForeignKey("metals.id"), nullable=False)
    currency_id: Mapped[UUID] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    unit_id: Mapped[UUID] = mapped_column(ForeignKey("units.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    metal: Mapped[MetalModel] = relationship()
    currency: Mapped[CurrencyModel] = relationship()
    unit: Mapped[UnitModel] = relationship()

    __table_args__ = (
        UniqueConstraint("symbol", "source"),
        Index("ix_reference_market_instruments_status", "status"),
    )


class InstrumentMappingModel(Base, TimestampMixin):
    __tablename__ = "instrument_mappings"

    id: Mapped[UUID] = uuid_pk()
    reference_market_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("reference_market_instruments.id"), nullable=False
    )
    execution_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_instruments.id"), nullable=False
    )
    fx_pair: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_conversion_rule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("unit_conversion_rules.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    reference_market_instrument: Mapped[ReferenceMarketInstrumentModel] = relationship()
    execution_instrument: Mapped[ExecutionInstrumentModel] = relationship()
    unit_conversion_rule: Mapped[UnitConversionRuleModel | None] = relationship()

    __table_args__ = (
        UniqueConstraint("reference_market_instrument_id", "execution_instrument_id"),
        Index("ix_instrument_mappings_reference", "reference_market_instrument_id"),
        Index("ix_instrument_mappings_execution", "execution_instrument_id"),
    )


class VirtualAccountModel(Base, TimestampMixin):
    __tablename__ = "virtual_accounts"

    id: Mapped[UUID] = uuid_pk()
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_currency_id: Mapped[UUID] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    execution_venue_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_venues.id"), nullable=False
    )
    starting_balance: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    user: Mapped[UserModel] = relationship(back_populates="virtual_accounts")
    base_currency: Mapped[CurrencyModel] = relationship()
    execution_venue: Mapped[ExecutionVenueModel] = relationship()
    wallets: Mapped[list["WalletModel"]] = relationship(back_populates="virtual_account")
    allowed_instruments: Mapped[list["VirtualAccountInstrumentModel"]] = relationship(
        back_populates="virtual_account"
    )

    __table_args__ = (
        CheckConstraint("starting_balance >= 0", name="starting_balance_non_negative"),
        Index("ix_virtual_accounts_user_status", "user_id", "status"),
    )


class VirtualAccountInstrumentModel(Base, TimestampMixin):
    __tablename__ = "virtual_account_instruments"

    id: Mapped[UUID] = uuid_pk()
    virtual_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("virtual_accounts.id"), nullable=False
    )
    execution_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_instruments.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    virtual_account: Mapped[VirtualAccountModel] = relationship(
        back_populates="allowed_instruments"
    )
    execution_instrument: Mapped[ExecutionInstrumentModel] = relationship()

    __table_args__ = (
        UniqueConstraint("virtual_account_id", "execution_instrument_id"),
        Index("ix_virtual_account_instruments_account", "virtual_account_id"),
    )


class WalletModel(Base, TimestampMixin):
    __tablename__ = "wallets"

    id: Mapped[UUID] = uuid_pk()
    virtual_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("virtual_accounts.id"), nullable=False
    )
    currency_id: Mapped[UUID] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    available_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    reserved_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)

    virtual_account: Mapped[VirtualAccountModel] = relationship(back_populates="wallets")
    currency: Mapped[CurrencyModel] = relationship()

    __table_args__ = (
        UniqueConstraint("virtual_account_id", "currency_id"),
        CheckConstraint("available_amount >= 0", name="available_amount_non_negative"),
        CheckConstraint("reserved_amount >= 0", name="reserved_amount_non_negative"),
    )


class PriceQuoteModel(Base, TimestampMixin):
    __tablename__ = "price_quotes"

    id: Mapped[UUID] = uuid_pk()
    bank_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("bank_instruments.id"), nullable=False
    )
    bank_buy_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    bank_sell_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    observed_at: Mapped[datetime] = utc_datetime()
    fetched_at: Mapped[datetime] = utc_datetime()
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    freshness_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")

    bank_instrument: Mapped[BankInstrumentModel] = relationship()

    __table_args__ = (
        CheckConstraint("bank_buy_price >= 0", name="bank_buy_price_non_negative"),
        CheckConstraint("bank_sell_price >= bank_buy_price", name="sell_price_gte_buy_price"),
        CheckConstraint("fetched_at >= observed_at", name="fetched_at_gte_observed_at"),
        Index("ix_price_quotes_instrument_observed", "bank_instrument_id", "observed_at"),
        Index("ix_price_quotes_fetched_at", "fetched_at"),
    )


class ExecutionPremiumSnapshotModel(Base, TimestampMixin):
    __tablename__ = "execution_premium_snapshots"

    id: Mapped[UUID] = uuid_pk()
    execution_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_instruments.id"), nullable=False
    )
    bank_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("bank_instruments.id"), nullable=False
    )
    price_quote_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("price_quotes.id"), nullable=True
    )
    reference_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    reference_currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    reference_unit_code: Mapped[str] = mapped_column(String(16), nullable=False)
    execution_currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    execution_unit_code: Mapped[str] = mapped_column(String(16), nullable=False)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    fx_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    unit_conversion: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    converted_reference_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    bank_buy_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    bank_sell_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    bank_spread: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    buy_discount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    sell_premium: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[datetime] = utc_datetime()

    execution_instrument: Mapped[ExecutionInstrumentModel] = relationship()
    bank_instrument: Mapped[BankInstrumentModel] = relationship()
    price_quote: Mapped[PriceQuoteModel | None] = relationship()

    __table_args__ = (
        CheckConstraint("reference_price > 0", name="premium_reference_price_positive"),
        CheckConstraint("bank_buy_price >= 0", name="premium_bank_buy_non_negative"),
        CheckConstraint("bank_sell_price >= bank_buy_price", name="premium_sell_gte_buy"),
        CheckConstraint("bank_spread >= 0", name="premium_spread_non_negative"),
        CheckConstraint(
            "fx_rate IS NULL OR fx_rate > 0",
            name="premium_fx_rate_positive",
        ),
        CheckConstraint(
            "status IN ('ok', 'missing_fx_rate')",
            name="premium_status_valid",
        ),
        Index("ix_execution_premium_instrument_captured", "execution_instrument_id", "captured_at"),
        Index("ix_execution_premium_status", "status"),
    )


class NewsSourceModel(Base, TimestampMixin):
    __tablename__ = "news_sources"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    reliability_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    source_policy: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    events: Mapped[list["NewsEventModel"]] = relationship(back_populates="source")

    __table_args__ = (
        CheckConstraint(
            "category IN ('central_bank', 'turkish_financial', 'global_financial', "
            "'commodity', 'economic_calendar')",
            name="news_source_category_valid",
        ),
        CheckConstraint(
            "reliability_score >= 0 AND reliability_score <= 1",
            name="news_source_reliability_range",
        ),
        Index("ix_news_sources_status", "status"),
    )


class NewsEventModel(Base, TimestampMixin):
    __tablename__ = "news_events"

    id: Mapped[UUID] = uuid_pk()
    source_id: Mapped[UUID] = mapped_column(ForeignKey("news_sources.id"), nullable=False)
    source_event_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    provider_reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime] = utc_datetime()
    fetched_at: Mapped[datetime] = utc_datetime()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    affected_assets: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    source: Mapped[NewsSourceModel] = relationship(back_populates="events")
    risk_snapshots: Mapped[list["EventRiskSnapshotModel"]] = relationship(
        back_populates="news_event"
    )

    __table_args__ = (
        UniqueConstraint("source_id", "content_hash"),
        CheckConstraint("fetched_at >= published_at", name="news_event_fetched_gte_published"),
        Index("ix_news_events_source_published", "source_id", "published_at"),
        Index("ix_news_events_event_type", "event_type"),
    )


class EventRiskSnapshotModel(Base, TimestampMixin):
    __tablename__ = "event_risk_snapshots"

    id: Mapped[UUID] = uuid_pk()
    news_event_id: Mapped[UUID] = mapped_column(ForeignKey("news_events.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    affected_assets: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    direction_bias: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    time_horizon: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    reasoning: Mapped[str] = mapped_column(String(1000), nullable=False)
    action_recommendation: Mapped[str] = mapped_column(String(32), nullable=False)
    interpreted_at: Mapped[datetime] = utc_datetime()
    expires_at: Mapped[datetime] = utc_datetime()
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)

    news_event: Mapped[NewsEventModel] = relationship(back_populates="risk_snapshots")

    __table_args__ = (
        UniqueConstraint("news_event_id", "schema_version"),
        CheckConstraint(
            "direction_bias IN ('bullish', 'bearish', 'neutral', 'mixed', 'unknown')",
            name="event_risk_direction_bias_valid",
        ),
        CheckConstraint(
            "time_horizon IN ('intraday', '1d', '1w', '1m', 'unknown')",
            name="event_risk_time_horizon_valid",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'unknown')",
            name="event_risk_level_valid",
        ),
        CheckConstraint(
            "action_recommendation IN ('veto', 'reduce_risk', 'no_trade', 'monitor', 'none')",
            name="event_risk_action_valid",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="event_risk_confidence_range"),
        CheckConstraint("expires_at > interpreted_at", name="event_risk_expiry_valid"),
        Index("ix_event_risk_snapshots_event", "news_event_id"),
        Index("ix_event_risk_snapshots_action", "action_recommendation"),
        Index("ix_event_risk_snapshots_expires", "expires_at"),
    )


class MarketBarModel(Base, TimestampMixin):
    __tablename__ = "market_bars"

    id: Mapped[UUID] = uuid_pk()
    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    quote_count: Mapped[int] = mapped_column(nullable=False)
    bar_start_at: Mapped[datetime] = utc_datetime()
    bar_end_at: Mapped[datetime] = utc_datetime()

    __table_args__ = (
        UniqueConstraint("instrument_type", "instrument_id", "timeframe", "bar_start_at"),
        CheckConstraint(
            "instrument_type IN ('reference', 'execution')", name="instrument_type_valid"
        ),
        CheckConstraint(
            "open >= 0 AND high >= 0 AND low >= 0 AND close >= 0", name="prices_non_negative"
        ),
        CheckConstraint("high >= open AND high >= close AND high >= low", name="high_is_highest"),
        CheckConstraint("low <= open AND low <= close AND low <= high", name="low_is_lowest"),
        CheckConstraint("quote_count > 0", name="quote_count_positive"),
        CheckConstraint("bar_end_at > bar_start_at", name="bar_window_valid"),
        Index("ix_market_bars_instrument_time", "instrument_type", "instrument_id", "bar_start_at"),
    )


class IndicatorSnapshotModel(Base, TimestampMixin):
    __tablename__ = "indicator_snapshots"

    id: Mapped[UUID] = uuid_pk()
    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    indicator_name: Mapped[str] = mapped_column(String(80), nullable=False)
    parameters_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    calculated_at: Mapped[datetime] = utc_datetime()
    source_bar_end_at: Mapped[datetime] = utc_datetime()

    __table_args__ = (
        UniqueConstraint(
            "instrument_type",
            "instrument_id",
            "source",
            "timeframe",
            "indicator_name",
            "parameters_hash",
            "source_bar_end_at",
        ),
        CheckConstraint(
            "instrument_type IN ('reference', 'execution')",
            name="indicator_instrument_type_valid",
        ),
        Index(
            "ix_indicator_snapshots_lookup",
            "instrument_type",
            "instrument_id",
            "timeframe",
            "indicator_name",
            "source_bar_end_at",
        ),
    )


class MarketRegimeSnapshotModel(Base, TimestampMixin):
    __tablename__ = "market_regime_snapshots"

    id: Mapped[UUID] = uuid_pk()
    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    regime: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    config_version: Mapped[str] = mapped_column(String(80), nullable=False)
    starts_at: Mapped[datetime] = utc_datetime()
    confirmed_at: Mapped[datetime] = utc_datetime()
    source_bar_end_at: Mapped[datetime] = utc_datetime()

    __table_args__ = (
        UniqueConstraint(
            "instrument_type",
            "instrument_id",
            "source",
            "timeframe",
            "source_bar_end_at",
            "config_version",
        ),
        CheckConstraint(
            "instrument_type IN ('reference', 'execution')",
            name="market_regime_instrument_type_valid",
        ),
        CheckConstraint(
            "regime IN ('trend_up', 'trend_down', 'range', 'high_volatility', "
            "'low_volatility', 'no_trade')",
            name="market_regime_value_valid",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="regime_confidence_range"),
        CheckConstraint("confirmed_at >= starts_at", name="regime_confirmed_gte_starts"),
        CheckConstraint(
            "confirmed_at >= source_bar_end_at",
            name="regime_confirmed_gte_source_bar_end",
        ),
        Index(
            "ix_market_regime_snapshots_lookup",
            "instrument_type",
            "instrument_id",
            "timeframe",
            "source_bar_end_at",
        ),
        Index("ix_market_regime_snapshots_confirmed", "confirmed_at"),
        Index("ix_market_regime_snapshots_regime", "regime"),
    )


class StrategyModel(Base, TimestampMixin):
    __tablename__ = "strategies"

    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)

    runs: Mapped[list["StrategyRunModel"]] = relationship(back_populates="strategy")

    __table_args__ = (
        UniqueConstraint("name", "version"),
        Index("ix_strategies_enabled", "enabled"),
    )


class StrategyRunModel(Base, TimestampMixin):
    __tablename__ = "strategy_runs"

    id: Mapped[UUID] = uuid_pk()
    strategy_id: Mapped[UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("virtual_accounts.id"), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    source_bar_end_at: Mapped[datetime] = utc_datetime()
    run_at: Mapped[datetime] = utc_datetime()
    regime_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("market_regime_snapshots.id"), nullable=True
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)

    strategy: Mapped[StrategyModel] = relationship(back_populates="runs")
    account: Mapped[VirtualAccountModel] = relationship()
    regime_snapshot: Mapped[MarketRegimeSnapshotModel | None] = relationship()
    trade_intents: Mapped[list["TradeIntentModel"]] = relationship(back_populates="strategy_run")

    __table_args__ = (
        CheckConstraint(
            "instrument_type IN ('reference', 'execution')",
            name="strategy_run_instrument_type_valid",
        ),
        CheckConstraint(
            "status IN ('intent_created', 'no_intent')",
            name="strategy_run_status_valid",
        ),
        CheckConstraint("run_at >= source_bar_end_at", name="strategy_run_at_gte_source_bar_end"),
        Index("ix_strategy_runs_strategy_time", "strategy_id", "run_at"),
        Index("ix_strategy_runs_account_time", "account_id", "run_at"),
    )


class TradeIntentModel(Base, TimestampMixin):
    __tablename__ = "trade_intents"

    id: Mapped[UUID] = uuid_pk()
    account_id: Mapped[UUID] = mapped_column(ForeignKey("virtual_accounts.id"), nullable=False)
    strategy_run_id: Mapped[UUID] = mapped_column(ForeignKey("strategy_runs.id"), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    cash_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    signal_time: Mapped[datetime] = utc_datetime()
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)

    account: Mapped[VirtualAccountModel] = relationship()
    strategy_run: Mapped[StrategyRunModel] = relationship(back_populates="trade_intents")
    risk_decisions: Mapped[list["RiskDecisionModel"]] = relationship(back_populates="trade_intent")

    __table_args__ = (
        CheckConstraint("side IN ('buy')", name="trade_intent_side_valid"),
        CheckConstraint(
            "status IN ('pending_risk')",
            name="trade_intent_status_valid",
        ),
        CheckConstraint("cash_amount > 0", name="trade_intent_cash_amount_positive"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="trade_intent_quantity_positive"),
        Index("ix_trade_intents_account_status", "account_id", "status"),
        Index("ix_trade_intents_strategy_run", "strategy_run_id"),
    )


class RiskDecisionModel(Base, TimestampMixin):
    __tablename__ = "risk_decisions"

    id: Mapped[UUID] = uuid_pk()
    trade_intent_id: Mapped[UUID] = mapped_column(ForeignKey("trade_intents.id"), nullable=False)
    execution_instrument_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("execution_instruments.id"), nullable=True
    )
    quote_id: Mapped[UUID | None] = mapped_column(ForeignKey("price_quotes.id"), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_cash_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    approved_cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    constraints_applied: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    evaluated_at: Mapped[datetime] = utc_datetime()

    trade_intent: Mapped[TradeIntentModel] = relationship(back_populates="risk_decisions")
    execution_instrument: Mapped[ExecutionInstrumentModel | None] = relationship()
    quote: Mapped[PriceQuoteModel | None] = relationship()

    __table_args__ = (
        UniqueConstraint("trade_intent_id", "policy_version"),
        CheckConstraint("decision IN ('approve', 'reduce', 'reject')", name="risk_decision_valid"),
        CheckConstraint("requested_cash_amount > 0", name="risk_requested_cash_amount_positive"),
        CheckConstraint(
            "approved_cash_amount IS NULL OR approved_cash_amount >= 0",
            name="risk_approved_cash_amount_non_negative",
        ),
        CheckConstraint(
            "approved_quantity IS NULL OR approved_quantity >= 0",
            name="risk_approved_quantity_non_negative",
        ),
        CheckConstraint(
            "approved_cash_amount IS NULL OR approved_cash_amount <= requested_cash_amount",
            name="risk_approved_cash_amount_lte_requested",
        ),
        Index("ix_risk_decisions_intent", "trade_intent_id"),
        Index("ix_risk_decisions_execution_instrument", "execution_instrument_id"),
        Index("ix_risk_decisions_decision", "decision"),
        Index("ix_risk_decisions_created_at", "created_at"),
    )


class PaperOrderModel(Base, TimestampMixin):
    __tablename__ = "paper_orders"

    id: Mapped[UUID] = uuid_pk()
    account_id: Mapped[UUID] = mapped_column(ForeignKey("virtual_accounts.id"), nullable=False)
    trade_intent_id: Mapped[UUID] = mapped_column(ForeignKey("trade_intents.id"), nullable=False)
    risk_decision_id: Mapped[UUID] = mapped_column(ForeignKey("risk_decisions.id"), nullable=False)
    execution_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_instruments.id"), nullable=False
    )
    bank_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("bank_instruments.id"), nullable=False
    )
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    approved_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    account: Mapped[VirtualAccountModel] = relationship()
    trade_intent: Mapped[TradeIntentModel] = relationship()
    risk_decision: Mapped[RiskDecisionModel] = relationship()
    execution_instrument: Mapped[ExecutionInstrumentModel] = relationship()
    bank_instrument: Mapped[BankInstrumentModel] = relationship()
    trade: Mapped["PaperTradeModel | None"] = relationship(back_populates="order")

    __table_args__ = (
        UniqueConstraint("risk_decision_id", name="uq_paper_orders_risk_decision_id"),
        CheckConstraint("side IN ('buy', 'sell')", name="paper_order_side_valid"),
        CheckConstraint(
            "status IN ('pending', 'executed', 'rejected')",
            name="paper_order_status_valid",
        ),
        CheckConstraint("requested_quantity > 0", name="paper_order_requested_quantity_positive"),
        CheckConstraint("approved_quantity > 0", name="paper_order_approved_quantity_positive"),
        Index("ix_paper_orders_account_status", "account_id", "status"),
        Index("ix_paper_orders_risk_decision", "risk_decision_id"),
    )


class PaperTradeModel(Base, TimestampMixin):
    __tablename__ = "paper_trades"

    id: Mapped[UUID] = uuid_pk()
    order_id: Mapped[UUID] = mapped_column(ForeignKey("paper_orders.id"), nullable=False)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("virtual_accounts.id"), nullable=False)
    execution_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_instruments.id"), nullable=False
    )
    bank_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("bank_instruments.id"), nullable=False
    )
    quote_id: Mapped[UUID] = mapped_column(ForeignKey("price_quotes.id"), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    execution_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    gross_cash_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    taxes: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    spread_cost: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    net_cash_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    cost_breakdown: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    executed_at: Mapped[datetime] = utc_datetime()

    order: Mapped[PaperOrderModel] = relationship(back_populates="trade")
    account: Mapped[VirtualAccountModel] = relationship()
    execution_instrument: Mapped[ExecutionInstrumentModel] = relationship()
    bank_instrument: Mapped[BankInstrumentModel] = relationship()
    quote: Mapped[PriceQuoteModel] = relationship()

    __table_args__ = (
        UniqueConstraint("order_id", name="uq_paper_trades_order_id"),
        CheckConstraint("side IN ('buy', 'sell')", name="paper_trade_side_valid"),
        CheckConstraint("quantity > 0", name="paper_trade_quantity_positive"),
        CheckConstraint("execution_price > 0", name="paper_trade_execution_price_positive"),
        CheckConstraint("gross_cash_amount >= 0", name="paper_trade_gross_non_negative"),
        CheckConstraint("fees >= 0", name="paper_trade_fees_non_negative"),
        CheckConstraint("taxes >= 0", name="paper_trade_taxes_non_negative"),
        CheckConstraint("spread_cost >= 0", name="paper_trade_spread_cost_non_negative"),
        Index("ix_paper_trades_account_executed", "account_id", "executed_at"),
        Index("ix_paper_trades_order", "order_id"),
    )


class PositionModel(Base, TimestampMixin):
    __tablename__ = "positions"

    id: Mapped[UUID] = uuid_pk()
    account_id: Mapped[UUID] = mapped_column(ForeignKey("virtual_accounts.id"), nullable=False)
    bank_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("bank_instruments.id"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)

    account: Mapped[VirtualAccountModel] = relationship()
    bank_instrument: Mapped[BankInstrumentModel] = relationship()

    __table_args__ = (
        UniqueConstraint("account_id", "bank_instrument_id", name="uq_positions_account_bank"),
        CheckConstraint("quantity >= 0", name="position_quantity_non_negative"),
        CheckConstraint("average_cost >= 0", name="position_average_cost_non_negative"),
        Index("ix_positions_account", "account_id"),
    )


class LedgerEntryModel(Base, TimestampMixin):
    __tablename__ = "ledger_entries"

    id: Mapped[UUID] = uuid_pk()
    account_id: Mapped[UUID] = mapped_column(ForeignKey("virtual_accounts.id"), nullable=False)
    currency_id: Mapped[UUID] = mapped_column(ForeignKey("currencies.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)

    account: Mapped[VirtualAccountModel] = relationship()
    currency: Mapped[CurrencyModel] = relationship()

    __table_args__ = (
        Index("ix_ledger_entries_account_created", "account_id", "created_at"),
        Index("ix_ledger_entries_reference", "reference_type", "reference_id"),
    )


class BacktestDatasetSnapshotModel(Base, TimestampMixin):
    __tablename__ = "backtest_dataset_snapshots"

    id: Mapped[UUID] = uuid_pk()
    instrument_type: Mapped[str] = mapped_column(String(16), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    execution_instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("execution_instruments.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    quote_source: Mapped[str] = mapped_column(String(200), nullable=False)
    start_at: Mapped[datetime] = utc_datetime()
    end_at: Mapped[datetime] = utc_datetime()
    input_ranges: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    execution_instrument: Mapped[ExecutionInstrumentModel] = relationship()

    __table_args__ = (
        CheckConstraint(
            "instrument_type IN ('reference', 'execution')",
            name="backtest_dataset_instrument_type_valid",
        ),
        CheckConstraint("end_at > start_at", name="backtest_dataset_window_valid"),
        Index(
            "ix_backtest_dataset_lookup",
            "instrument_type",
            "instrument_id",
            "timeframe",
            "start_at",
            "end_at",
        ),
    )


class BacktestRunModel(Base, TimestampMixin):
    __tablename__ = "backtest_runs"

    id: Mapped[UUID] = uuid_pk()
    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("backtest_dataset_snapshots.id"), nullable=False
    )
    account_id: Mapped[UUID] = mapped_column(ForeignKey("virtual_accounts.id"), nullable=False)
    strategy_id: Mapped[UUID] = mapped_column(ForeignKey("strategies.id"), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = utc_datetime()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)

    dataset_snapshot: Mapped[BacktestDatasetSnapshotModel] = relationship()
    account: Mapped[VirtualAccountModel] = relationship()
    strategy: Mapped[StrategyModel] = relationship()

    __table_args__ = (
        CheckConstraint("status IN ('completed', 'failed')", name="backtest_run_status_valid"),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="backtest_completed_gte_started",
        ),
        Index("ix_backtest_runs_dataset", "dataset_snapshot_id"),
        Index("ix_backtest_runs_account", "account_id"),
        Index("ix_backtest_runs_strategy", "strategy_id"),
    )


class MLDatasetSnapshotModel(Base, TimestampMixin):
    __tablename__ = "ml_dataset_snapshots"

    id: Mapped[UUID] = uuid_pk()
    source_dataset_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("backtest_dataset_snapshots.id"), nullable=False
    )
    feature_spec: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    label_spec: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    split_spec: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    start_at: Mapped[datetime] = utc_datetime()
    end_at: Mapped[datetime] = utc_datetime()
    row_count: Mapped[int] = mapped_column(nullable=False)
    class_balance: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    artifact_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    source_dataset_snapshot: Mapped[BacktestDatasetSnapshotModel] = relationship()
    experiment_runs: Mapped[list["MLExperimentRunModel"]] = relationship(
        back_populates="dataset_snapshot"
    )

    __table_args__ = (
        CheckConstraint("end_at > start_at", name="ml_dataset_window_valid"),
        CheckConstraint("row_count >= 0", name="ml_dataset_row_count_non_negative"),
        Index("ix_ml_dataset_source", "source_dataset_snapshot_id"),
        Index("ix_ml_dataset_lookup", "start_at", "end_at", "row_count"),
    )


class MLExperimentRunModel(Base, TimestampMixin):
    __tablename__ = "ml_experiment_runs"

    id: Mapped[UUID] = uuid_pk()
    dataset_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("ml_dataset_snapshots.id"), nullable=False
    )
    model_family: Mapped[str] = mapped_column(String(80), nullable=False)
    hyperparameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    random_seed: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = utc_datetime()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)

    dataset_snapshot: Mapped[MLDatasetSnapshotModel] = relationship(
        back_populates="experiment_runs"
    )
    metrics: Mapped[list["MLExperimentMetricModel"]] = relationship(back_populates="run")

    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'failed', 'insufficient_data')",
            name="ml_experiment_status_valid",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ml_experiment_completed_gte_started",
        ),
        Index("ix_ml_experiment_runs_dataset", "dataset_snapshot_id"),
        Index("ix_ml_experiment_runs_model_status", "model_family", "status"),
    )


class MLExperimentMetricModel(Base, TimestampMixin):
    __tablename__ = "ml_experiment_metrics"

    id: Mapped[UUID] = uuid_pk()
    experiment_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("ml_experiment_runs.id"), nullable=False
    )
    split: Mapped[str] = mapped_column(String(40), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(120), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    metric_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)

    run: Mapped[MLExperimentRunModel] = relationship(back_populates="metrics")

    __table_args__ = (
        UniqueConstraint(
            "experiment_run_id",
            "split",
            "metric_name",
            name="uq_ml_experiment_metrics_run_split_metric",
        ),
        Index("ix_ml_experiment_metrics_run", "experiment_run_id"),
        Index("ix_ml_experiment_metrics_name", "metric_name"),
    )


@event.listens_for(LedgerEntryModel, "before_update")
def _prevent_ledger_entry_update(
    _mapper: object,
    _connection: object,
    _target: LedgerEntryModel,
) -> None:
    raise ValueError("ledger entries are append-only")
