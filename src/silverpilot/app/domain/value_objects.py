from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from silverpilot.app.domain.enums import (
    EndpointStatus,
    ExecutionSourcePolicy,
    IndicatorSourcePolicy,
    InstrumentType,
    MarketSessionStatus,
    QuoteUsability,
    SourcePurpose,
    SourceRole,
)


def parse_decimal(value: Any) -> Decimal:
    if isinstance(value, float):
        raise ValueError("float values are not allowed; use Decimal or string")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | str):
        return Decimal(str(value))
    raise ValueError("value must be Decimal, int, or string")


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Decimal
    currency_code: str

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: Any) -> Decimal:
        return parse_decimal(value)

    @field_validator("currency_code")
    @classmethod
    def validate_currency_code(cls, value: str) -> str:
        normalized = value.upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("currency_code must be a three-letter code")
        return normalized

    @model_validator(mode="after")
    def validate_non_negative(self) -> "Money":
        if self.amount < Decimal("0"):
            raise ValueError("money amount cannot be negative")
        return self


class Quantity(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Decimal
    unit_code: str

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: Any) -> Decimal:
        return parse_decimal(value)

    @field_validator("unit_code")
    @classmethod
    def validate_unit_code(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized or len(normalized) > 16:
            raise ValueError("unit_code must be 1-16 characters")
        return normalized

    @model_validator(mode="after")
    def validate_non_negative(self) -> "Quantity":
        if self.amount < Decimal("0"):
            raise ValueError("quantity amount cannot be negative")
        return self


class SourcePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_role: SourceRole
    indicator_source_policy: IndicatorSourcePolicy = IndicatorSourcePolicy.REFERENCE_MARKET_FIRST
    execution_source_policy: ExecutionSourcePolicy = ExecutionSourcePolicy.ACCOUNT_BOUND_BANK_QUOTE


class MarketSessionCalendar(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    timezone: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("calendar code is required")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("timezone is required")
        return normalized


class InstrumentSessionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    instrument_type: InstrumentType
    instrument_id: UUID
    venue_id: UUID | None = None
    calendar: MarketSessionCalendar

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("source is required")
        return normalized


class SessionDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    instrument_type: InstrumentType
    instrument_id: UUID
    purpose: SourcePurpose
    endpoint_status: EndpointStatus = EndpointStatus.UNKNOWN
    market_session_status: MarketSessionStatus = MarketSessionStatus.UNKNOWN
    quote_usability: QuoteUsability = QuoteUsability.UNKNOWN
    eligible: bool
    reason: str
    decided_at: datetime
    venue_id: UUID | None = None

    @field_validator("source", "reason")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized
