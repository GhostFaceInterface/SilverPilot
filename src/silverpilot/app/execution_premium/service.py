from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import (
    BankInstrumentModel,
    ExecutionInstrumentModel,
    ExecutionPremiumSnapshotModel,
    PriceQuoteModel,
    UnitConversionRuleModel,
)

_MONEY_QUANTUM = Decimal("0.00000001")


class UnitConversionError(ValueError):
    pass


@dataclass(frozen=True)
class UnitConversionResult:
    value: Decimal
    factor: Decimal
    rule_id: UUID | None
    from_unit_id: UUID
    to_unit_id: UUID
    effective_at: datetime

    def to_json(self) -> dict[str, object]:
        return {
            "value": str(self.value),
            "factor": str(self.factor),
            "rule_id": str(self.rule_id) if self.rule_id is not None else None,
            "from_unit_id": str(self.from_unit_id),
            "to_unit_id": str(self.to_unit_id),
            "effective_at": self.effective_at.isoformat(),
        }


class DatabaseUnitConversionService:
    def __init__(self, *, session: Session) -> None:
        self._session = session

    def convert(
        self,
        *,
        value: Decimal,
        from_unit_id: UUID,
        to_unit_id: UUID,
        effective_at: datetime,
    ) -> UnitConversionResult:
        effective = _aware_utc(effective_at)
        if from_unit_id == to_unit_id:
            return UnitConversionResult(
                value=value,
                factor=Decimal("1"),
                rule_id=None,
                from_unit_id=from_unit_id,
                to_unit_id=to_unit_id,
                effective_at=effective,
            )

        rules = list(
            self._session.scalars(
                select(UnitConversionRuleModel)
                .where(
                    UnitConversionRuleModel.from_unit_id == from_unit_id,
                    UnitConversionRuleModel.to_unit_id == to_unit_id,
                    UnitConversionRuleModel.effective_from <= effective,
                )
                .where(
                    (UnitConversionRuleModel.effective_to.is_(None))
                    | (UnitConversionRuleModel.effective_to > effective)
                )
                .order_by(UnitConversionRuleModel.effective_from.desc(), UnitConversionRuleModel.id)
            )
        )
        if not rules:
            raise UnitConversionError("missing_unit_conversion_rule")
        if len(rules) > 1:
            raise UnitConversionError("ambiguous_unit_conversion_rule")
        rule = rules[0]
        factor = Decimal(rule.factor)
        return UnitConversionResult(
            value=value * factor,
            factor=factor,
            rule_id=rule.id,
            from_unit_id=from_unit_id,
            to_unit_id=to_unit_id,
            effective_at=effective,
        )


@dataclass(frozen=True)
class ExecutionPremiumInput:
    execution_instrument_id: UUID
    reference_price: Decimal
    reference_currency_code: str
    reference_unit_code: str
    bank_buy_price: Decimal
    bank_sell_price: Decimal
    captured_at: datetime
    price_quote_id: UUID | None = None
    fx_rate: Decimal | None = None
    fx_source: str | None = None
    unit_conversion: UnitConversionResult | None = None
    provenance: dict[str, object] | None = None


class ExecutionPremiumService:
    def __init__(self, *, session: Session) -> None:
        self._session = session

    def create_snapshot(self, data: ExecutionPremiumInput) -> ExecutionPremiumSnapshotModel:
        if data.reference_price <= Decimal("0"):
            raise ValueError("reference_price must be positive")
        if data.bank_buy_price < Decimal("0"):
            raise ValueError("bank_buy_price cannot be negative")
        if data.bank_sell_price < data.bank_buy_price:
            raise ValueError("bank_sell_price cannot be lower than bank_buy_price")

        execution_instrument = self._session.get(
            ExecutionInstrumentModel, data.execution_instrument_id
        )
        if execution_instrument is None:
            raise ValueError(f"execution instrument was not found: {data.execution_instrument_id}")
        if execution_instrument.bank_instrument_id is None:
            raise ValueError("execution instrument has no bank instrument")
        bank_instrument = self._session.get(
            BankInstrumentModel, execution_instrument.bank_instrument_id
        )
        if bank_instrument is None:
            raise ValueError("execution instrument bank instrument was not found")

        quote = (
            self._session.get(PriceQuoteModel, data.price_quote_id) if data.price_quote_id else None
        )
        if quote is not None and quote.bank_instrument_id != bank_instrument.id:
            raise ValueError("price quote does not match execution instrument")

        captured_at = _aware_utc(data.captured_at)
        execution_currency = execution_instrument.currency.code
        execution_unit = execution_instrument.unit.code
        fx_required = data.reference_currency_code != execution_currency
        status = "missing_fx_rate" if fx_required and data.fx_rate is None else "ok"
        converted_reference_price: Decimal | None = None
        buy_discount: Decimal | None = None
        sell_premium: Decimal | None = None
        if status == "ok":
            fx_rate = data.fx_rate if fx_required else Decimal("1")
            if fx_rate is None or fx_rate <= Decimal("0"):
                raise ValueError("fx_rate must be positive when supplied")
            unit_factor = (
                data.unit_conversion.factor if data.unit_conversion is not None else Decimal("1")
            )
            converted_reference_price = _money(data.reference_price * fx_rate * unit_factor)
            buy_discount = _money(converted_reference_price - data.bank_buy_price)
            sell_premium = _money(data.bank_sell_price - converted_reference_price)

        snapshot = ExecutionPremiumSnapshotModel(
            id=uuid4(),
            execution_instrument_id=execution_instrument.id,
            bank_instrument_id=bank_instrument.id,
            price_quote_id=data.price_quote_id,
            reference_price=data.reference_price,
            reference_currency_code=data.reference_currency_code,
            reference_unit_code=data.reference_unit_code,
            execution_currency_code=execution_currency,
            execution_unit_code=execution_unit,
            fx_rate=data.fx_rate,
            fx_source=data.fx_source,
            unit_conversion=(
                data.unit_conversion.to_json() if data.unit_conversion is not None else None
            ),
            converted_reference_price=converted_reference_price,
            bank_buy_price=data.bank_buy_price,
            bank_sell_price=data.bank_sell_price,
            bank_spread=_money(data.bank_sell_price - data.bank_buy_price),
            buy_discount=buy_discount,
            sell_premium=sell_premium,
            status=status,
            provenance={
                "reference_currency_code": data.reference_currency_code,
                "reference_unit_code": data.reference_unit_code,
                "fx_required": fx_required,
                **(data.provenance or {}),
            },
            captured_at=captured_at,
            created_at=captured_at,
        )
        self._session.add(snapshot)
        self._session.flush()
        return snapshot


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
