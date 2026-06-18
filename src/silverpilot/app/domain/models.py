from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from silverpilot.app.domain.enums import (
    AccountStatus,
    BankStatus,
    InstrumentType,
    MarketRegime,
    PaperOrderSide,
    PaperOrderStatus,
    RiskDecisionOutcome,
    StrategyRunStatus,
    TradeIntentSide,
    TradeIntentStatus,
)
from silverpilot.app.domain.value_objects import Money, parse_decimal


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True)


def _require_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class Currency(DomainModel):
    code: str
    name: str
    decimal_places: int = Field(ge=0, le=8)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency code must be a three-letter code")
        return normalized


class Metal(DomainModel):
    code: str
    name: str
    default_unit_code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.upper()
        if len(normalized) < 2 or len(normalized) > 8:
            raise ValueError("metal code must be 2-8 characters")
        return normalized


class Unit(DomainModel):
    code: str
    name: str
    precision: int = Field(ge=0, le=12)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized or len(normalized) > 16:
            raise ValueError("unit code must be 1-16 characters")
        return normalized


class Bank(DomainModel):
    id: UUID
    code: str
    name: str
    country_code: str
    status: BankStatus = BankStatus.ACTIVE

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.lower()
        if not normalized:
            raise ValueError("bank code is required")
        return normalized

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, value: str) -> str:
        normalized = value.upper()
        if len(normalized) != 2 or not normalized.isalpha():
            raise ValueError("country_code must be a two-letter code")
        return normalized


class BankInstrument(DomainModel):
    id: UUID
    bank_id: UUID
    metal_code: str
    unit_code: str
    currency_code: str
    symbol: str
    min_trade_amount: Money
    quantity_precision: int = Field(ge=0, le=12)
    price_precision: int = Field(ge=0, le=8)
    active: bool = True

    @field_validator("metal_code", "unit_code", "currency_code")
    @classmethod
    def validate_codes(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized:
            raise ValueError("code fields cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_currency_alignment(self) -> "BankInstrument":
        if self.min_trade_amount.currency_code != self.currency_code:
            raise ValueError("min_trade_amount currency must match instrument currency")
        return self


class PriceQuote(DomainModel):
    id: UUID
    bank_instrument_id: UUID
    bank_buy_price: Money
    bank_sell_price: Money
    observed_at: datetime
    fetched_at: datetime
    source: str

    @field_validator("observed_at", "fetched_at")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)

    @model_validator(mode="after")
    def validate_quote(self) -> "PriceQuote":
        if self.bank_buy_price.currency_code != self.bank_sell_price.currency_code:
            raise ValueError("buy and sell prices must use the same currency")
        if self.bank_sell_price.amount < self.bank_buy_price.amount:
            raise ValueError("bank sell price cannot be lower than bank buy price")
        if self.observed_at > self.fetched_at:
            raise ValueError("observed_at cannot be after fetched_at")
        if not self.source.strip():
            raise ValueError("source is required")
        return self


class MarketBar(DomainModel):
    id: UUID
    instrument_type: InstrumentType
    instrument_id: UUID
    source: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    quote_count: int = Field(gt=0)
    bar_start_at: datetime
    bar_end_at: datetime

    @field_validator("open", "high", "low", "close", mode="before")
    @classmethod
    def validate_decimal(cls, value: Any) -> Decimal:
        return parse_decimal(value)

    @field_validator("bar_start_at", "bar_end_at")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)

    @model_validator(mode="after")
    def validate_bar(self) -> "MarketBar":
        if self.bar_start_at >= self.bar_end_at:
            raise ValueError("bar_start_at must be before bar_end_at")
        if min(self.open, self.close, self.low) < Decimal("0"):
            raise ValueError("bar prices cannot be negative")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be at least open, close, and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be no greater than open, close, and high")
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.timeframe.strip():
            raise ValueError("timeframe is required")
        return self


class IndicatorSnapshot(DomainModel):
    id: UUID
    instrument_type: InstrumentType
    instrument_id: UUID
    source: str
    timeframe: str
    indicator_name: str
    parameters: dict[str, Any]
    value: Decimal
    calculated_at: datetime
    source_bar_end_at: datetime

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: Any) -> Decimal:
        return parse_decimal(value)

    @field_validator("calculated_at", "source_bar_end_at")
    @classmethod
    def validate_datetime(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)

    @field_validator("indicator_name")
    @classmethod
    def validate_indicator_name(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("indicator_name is required")
        return normalized

    @model_validator(mode="after")
    def validate_snapshot(self) -> "IndicatorSnapshot":
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.timeframe.strip():
            raise ValueError("timeframe is required")
        if self.source_bar_end_at > self.calculated_at:
            raise ValueError("source_bar_end_at cannot be after calculated_at")
        return self


class MarketRegimeSnapshot(DomainModel):
    id: UUID
    instrument_type: InstrumentType
    instrument_id: UUID
    source: str
    timeframe: str
    regime: MarketRegime
    confidence: Decimal
    evidence: dict[str, Any]
    config_version: str
    starts_at: datetime
    confirmed_at: datetime
    source_bar_end_at: datetime

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, value: Any) -> Decimal:
        parsed = parse_decimal(value)
        if parsed < Decimal("0") or parsed > Decimal("1"):
            raise ValueError("confidence must be between 0 and 1")
        return parsed

    @field_validator("starts_at", "confirmed_at", "source_bar_end_at")
    @classmethod
    def validate_regime_datetime(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)

    @model_validator(mode="after")
    def validate_regime_snapshot(self) -> "MarketRegimeSnapshot":
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.timeframe.strip():
            raise ValueError("timeframe is required")
        if not self.config_version.strip():
            raise ValueError("config_version is required")
        if self.source_bar_end_at > self.confirmed_at:
            raise ValueError("source_bar_end_at cannot be after confirmed_at")
        if self.starts_at > self.confirmed_at:
            raise ValueError("starts_at cannot be after confirmed_at")
        return self


class StrategyDefinition(DomainModel):
    id: UUID
    name: str
    version: str
    parameters: dict[str, Any]
    enabled: bool = True

    @field_validator("name", "version")
    @classmethod
    def validate_strategy_identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("strategy identity fields are required")
        return normalized


class StrategyRun(DomainModel):
    id: UUID
    strategy_id: UUID
    account_id: UUID
    instrument_type: InstrumentType
    instrument_id: UUID
    source: str
    timeframe: str
    source_bar_end_at: datetime
    run_at: datetime
    regime_snapshot_id: UUID | None = None
    input_hash: str
    status: StrategyRunStatus
    evidence: dict[str, Any]

    @field_validator("source_bar_end_at", "run_at")
    @classmethod
    def validate_strategy_run_datetime(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)

    @model_validator(mode="after")
    def validate_strategy_run(self) -> "StrategyRun":
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.timeframe.strip():
            raise ValueError("timeframe is required")
        if not self.input_hash.strip():
            raise ValueError("input_hash is required")
        if self.source_bar_end_at > self.run_at:
            raise ValueError("source_bar_end_at cannot be after run_at")
        return self


class TradeIntent(DomainModel):
    id: UUID
    account_id: UUID
    strategy_run_id: UUID
    side: TradeIntentSide
    cash_amount: Decimal
    quantity: Decimal | None = None
    signal_time: datetime
    status: TradeIntentStatus
    rationale: str
    evidence: dict[str, Any]

    @field_validator("cash_amount", "quantity", mode="before")
    @classmethod
    def validate_intent_decimal(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        parsed = parse_decimal(value)
        if parsed <= Decimal("0"):
            raise ValueError("intent amounts must be greater than zero")
        return parsed

    @field_validator("signal_time")
    @classmethod
    def validate_signal_time(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)

    @model_validator(mode="after")
    def validate_trade_intent(self) -> "TradeIntent":
        if not self.rationale.strip():
            raise ValueError("rationale is required")
        return self


class RiskDecision(DomainModel):
    id: UUID
    trade_intent_id: UUID
    execution_instrument_id: UUID | None = None
    quote_id: UUID | None = None
    decision: RiskDecisionOutcome
    requested_cash_amount: Decimal
    approved_cash_amount: Decimal | None = None
    approved_quantity: Decimal | None = None
    policy_version: str
    reasons: list[str]
    constraints_applied: dict[str, Any]
    evaluated_at: datetime

    @field_validator(
        "requested_cash_amount",
        "approved_cash_amount",
        "approved_quantity",
        mode="before",
    )
    @classmethod
    def validate_risk_decimal(cls, value: Any) -> Decimal | None:
        if value is None:
            return None
        parsed = parse_decimal(value)
        if parsed < Decimal("0"):
            raise ValueError("risk amounts cannot be negative")
        return parsed

    @field_validator("evaluated_at")
    @classmethod
    def validate_evaluated_at(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)

    @model_validator(mode="after")
    def validate_risk_decision(self) -> "RiskDecision":
        if not self.policy_version.strip():
            raise ValueError("policy_version is required")
        if not self.reasons:
            raise ValueError("reasons are required")
        if self.requested_cash_amount <= Decimal("0"):
            raise ValueError("requested_cash_amount must be greater than zero")
        if self.decision == RiskDecisionOutcome.REJECT:
            if self.approved_cash_amount not in (None, Decimal("0")):
                raise ValueError("rejected decisions cannot approve cash")
            if self.approved_quantity not in (None, Decimal("0")):
                raise ValueError("rejected decisions cannot approve quantity")
        else:
            if self.approved_cash_amount is None or self.approved_cash_amount <= Decimal("0"):
                raise ValueError("approved decisions require positive approved cash")
            if self.approved_quantity is None or self.approved_quantity <= Decimal("0"):
                raise ValueError("approved decisions require positive approved quantity")
            if self.approved_cash_amount > self.requested_cash_amount:
                raise ValueError("approved_cash_amount cannot exceed requested_cash_amount")
        return self


class PaperOrder(DomainModel):
    id: UUID
    account_id: UUID
    trade_intent_id: UUID
    risk_decision_id: UUID
    execution_instrument_id: UUID
    bank_instrument_id: UUID
    side: PaperOrderSide
    requested_quantity: Decimal
    approved_quantity: Decimal
    status: PaperOrderStatus

    @field_validator("requested_quantity", "approved_quantity", mode="before")
    @classmethod
    def validate_order_quantity(cls, value: Any) -> Decimal:
        parsed = parse_decimal(value)
        if parsed <= Decimal("0"):
            raise ValueError("paper order quantities must be greater than zero")
        return parsed


class PaperTrade(DomainModel):
    id: UUID
    order_id: UUID
    account_id: UUID
    execution_instrument_id: UUID
    bank_instrument_id: UUID
    quote_id: UUID
    side: PaperOrderSide
    quantity: Decimal
    execution_price: Decimal
    gross_cash_amount: Decimal
    fees: Decimal
    taxes: Decimal
    spread_cost: Decimal
    net_cash_amount: Decimal
    realized_pnl: Decimal
    executed_at: datetime

    @field_validator(
        "quantity",
        "execution_price",
        "gross_cash_amount",
        "fees",
        "taxes",
        "spread_cost",
        "net_cash_amount",
        "realized_pnl",
        mode="before",
    )
    @classmethod
    def validate_trade_decimal(cls, value: Any) -> Decimal:
        return parse_decimal(value)

    @field_validator("executed_at")
    @classmethod
    def validate_executed_at(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)

    @model_validator(mode="after")
    def validate_trade(self) -> "PaperTrade":
        if self.quantity <= Decimal("0"):
            raise ValueError("trade quantity must be greater than zero")
        if self.execution_price <= Decimal("0"):
            raise ValueError("execution_price must be greater than zero")
        for field_name in ("gross_cash_amount", "fees", "taxes", "spread_cost"):
            if getattr(self, field_name) < Decimal("0"):
                raise ValueError(f"{field_name} cannot be negative")
        return self


class Position(DomainModel):
    id: UUID
    account_id: UUID
    bank_instrument_id: UUID
    quantity: Decimal
    average_cost: Decimal
    realized_pnl: Decimal

    @field_validator("quantity", "average_cost", "realized_pnl", mode="before")
    @classmethod
    def validate_position_decimal(cls, value: Any) -> Decimal:
        return parse_decimal(value)

    @model_validator(mode="after")
    def validate_position(self) -> "Position":
        if self.quantity < Decimal("0"):
            raise ValueError("position quantity cannot be negative")
        if self.average_cost < Decimal("0"):
            raise ValueError("position average_cost cannot be negative")
        return self


class LedgerEntry(DomainModel):
    id: UUID
    account_id: UUID
    currency_id: UUID
    amount: Decimal
    entry_type: str
    reference_type: str
    reference_id: UUID
    metadata_json: dict[str, Any]

    @field_validator("amount", mode="before")
    @classmethod
    def validate_entry_amount(cls, value: Any) -> Decimal:
        return parse_decimal(value)

    @model_validator(mode="after")
    def validate_entry(self) -> "LedgerEntry":
        if not self.entry_type.strip():
            raise ValueError("entry_type is required")
        if not self.reference_type.strip():
            raise ValueError("reference_type is required")
        return self


class User(DomainModel):
    id: UUID
    email: str | None = None
    external_id: str | None = None
    status: AccountStatus = AccountStatus.ACTIVE

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("email must contain @")
        return normalized

    @model_validator(mode="after")
    def validate_identity(self) -> "User":
        if self.email is None and not self.external_id:
            raise ValueError("user must have email or external_id")
        return self


class VirtualAccount(DomainModel):
    id: UUID
    user_id: UUID
    name: str
    base_currency_code: str
    execution_venue_id: UUID
    allowed_execution_instrument_ids: tuple[UUID, ...]
    starting_balance: Money
    status: AccountStatus = AccountStatus.ACTIVE

    @field_validator("base_currency_code")
    @classmethod
    def validate_base_currency_code(cls, value: str) -> str:
        normalized = value.upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("base_currency_code must be a three-letter code")
        return normalized

    @model_validator(mode="after")
    def validate_execution_context(self) -> "VirtualAccount":
        if not self.name.strip():
            raise ValueError("account name is required")
        if not self.allowed_execution_instrument_ids:
            raise ValueError("virtual account must have allowed execution instruments")
        if self.starting_balance.currency_code != self.base_currency_code:
            raise ValueError("starting balance currency must match base currency")
        return self
