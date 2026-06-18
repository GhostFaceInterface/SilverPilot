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
