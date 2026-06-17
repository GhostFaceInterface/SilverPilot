from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from silverpilot.app.domain.enums import AccountStatus, BankStatus, InstrumentType
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
