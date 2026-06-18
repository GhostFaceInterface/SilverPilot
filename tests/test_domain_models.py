from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from silverpilot.app.domain import (
    BankInstrument,
    Currency,
    IndicatorSnapshot,
    MarketBar,
    MarketRegimeSnapshot,
    Money,
    PriceQuote,
    Quantity,
    Unit,
    VirtualAccount,
)
from silverpilot.app.domain.enums import InstrumentType, MarketRegime


def test_money_uses_decimal_and_rejects_float() -> None:
    money = Money(amount="10.25", currency_code="try")

    assert money.amount == Decimal("10.25")
    assert money.currency_code == "TRY"

    with pytest.raises(ValidationError):
        Money(amount=10.25, currency_code="TRY")


def test_quantity_uses_decimal_and_rejects_float() -> None:
    quantity = Quantity(amount="31.1034768", unit_code="gram")

    assert quantity.amount == Decimal("31.1034768")
    assert quantity.unit_code == "GRAM"

    with pytest.raises(ValidationError):
        Quantity(amount=1.5, unit_code="GRAM")


def test_currency_precision_validation() -> None:
    currency = Currency(code="try", name="Turkish Lira", decimal_places=2)

    assert currency.code == "TRY"
    assert currency.decimal_places == 2

    with pytest.raises(ValidationError):
        Currency(code="TRY", name="Turkish Lira", decimal_places=20)


def test_unit_identity_validation() -> None:
    unit = Unit(code="gram", name="Gram", precision=6)

    assert unit.code == "GRAM"
    assert unit.precision == 6


def test_bank_instrument_construction_requires_matching_currency() -> None:
    bank_id = uuid4()
    instrument = BankInstrument(
        id=uuid4(),
        bank_id=bank_id,
        metal_code="xag",
        unit_code="gram",
        currency_code="try",
        symbol="KT-XAG-GRAM-TRY",
        min_trade_amount=Money(amount="100", currency_code="TRY"),
        quantity_precision=4,
        price_precision=4,
    )

    assert instrument.bank_id == bank_id
    assert instrument.metal_code == "XAG"
    assert instrument.unit_code == "GRAM"
    assert instrument.currency_code == "TRY"

    with pytest.raises(ValidationError):
        BankInstrument(
            id=uuid4(),
            bank_id=bank_id,
            metal_code="XAG",
            unit_code="GRAM",
            currency_code="TRY",
            symbol="KT-XAG-GRAM-TRY",
            min_trade_amount=Money(amount="100", currency_code="USD"),
            quantity_precision=4,
            price_precision=4,
        )


def test_price_quote_buy_sell_validation() -> None:
    now = datetime(2026, 6, 17, 10, 0, tzinfo=UTC)
    quote = PriceQuote(
        id=uuid4(),
        bank_instrument_id=uuid4(),
        bank_buy_price=Money(amount="41.10", currency_code="TRY"),
        bank_sell_price=Money(amount="42.20", currency_code="TRY"),
        observed_at=now,
        fetched_at=now + timedelta(seconds=1),
        source="fixture",
    )

    assert quote.bank_sell_price.amount > quote.bank_buy_price.amount

    with pytest.raises(ValidationError):
        PriceQuote(
            id=uuid4(),
            bank_instrument_id=uuid4(),
            bank_buy_price=Money(amount="42.20", currency_code="TRY"),
            bank_sell_price=Money(amount="41.10", currency_code="TRY"),
            observed_at=now,
            fetched_at=now + timedelta(seconds=1),
            source="fixture",
        )


def test_market_bar_timestamp_and_price_validation() -> None:
    start = datetime(2026, 6, 17, 10, 0, tzinfo=UTC)
    bar = MarketBar(
        id=uuid4(),
        instrument_type=InstrumentType.REFERENCE,
        instrument_id=uuid4(),
        source="reference-fixture",
        timeframe="1h",
        open="41.00",
        high="43.00",
        low="40.50",
        close="42.00",
        quote_count=4,
        bar_start_at=start,
        bar_end_at=start + timedelta(hours=1),
    )

    assert bar.instrument_type == InstrumentType.REFERENCE
    assert bar.open == Decimal("41.00")

    with pytest.raises(ValidationError):
        MarketBar(
            id=uuid4(),
            instrument_type=InstrumentType.EXECUTION,
            instrument_id=uuid4(),
            source="execution-fixture",
            timeframe="1h",
            open="41.00",
            high="40.00",
            low="40.50",
            close="42.00",
            quote_count=4,
            bar_start_at=start,
            bar_end_at=start + timedelta(hours=1),
        )


def test_indicator_snapshot_timestamp_validation() -> None:
    source_bar_end_at = datetime(2026, 6, 17, 11, 0, tzinfo=UTC)
    snapshot = IndicatorSnapshot(
        id=uuid4(),
        instrument_type=InstrumentType.REFERENCE,
        instrument_id=uuid4(),
        source="reference-fixture",
        timeframe="1h",
        indicator_name="EMA",
        parameters={"period": 14},
        value="42.125",
        calculated_at=source_bar_end_at + timedelta(seconds=1),
        source_bar_end_at=source_bar_end_at,
    )

    assert snapshot.indicator_name == "ema"
    assert snapshot.value == Decimal("42.125")

    with pytest.raises(ValidationError):
        IndicatorSnapshot(
            id=uuid4(),
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=uuid4(),
            source="reference-fixture",
            timeframe="1h",
            indicator_name="ema",
            parameters={"period": 14},
            value="42.125",
            calculated_at=source_bar_end_at,
            source_bar_end_at=source_bar_end_at + timedelta(seconds=1),
        )


def test_market_regime_snapshot_validation() -> None:
    source_bar_end_at = datetime(2026, 6, 17, 11, 0, tzinfo=UTC)
    snapshot = MarketRegimeSnapshot(
        id=uuid4(),
        instrument_type=InstrumentType.REFERENCE,
        instrument_id=uuid4(),
        source="reference-fixture",
        timeframe="1h",
        regime=MarketRegime.TREND_UP,
        confidence="0.85",
        evidence={"candidate_regime": "trend_up"},
        config_version="rule-v1",
        starts_at=source_bar_end_at,
        confirmed_at=source_bar_end_at + timedelta(seconds=1),
        source_bar_end_at=source_bar_end_at,
    )

    assert snapshot.confidence == Decimal("0.85")
    assert snapshot.regime == MarketRegime.TREND_UP

    with pytest.raises(ValidationError):
        MarketRegimeSnapshot(
            id=uuid4(),
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=uuid4(),
            source="reference-fixture",
            timeframe="1h",
            regime=MarketRegime.TREND_UP,
            confidence="1.25",
            evidence={},
            config_version="rule-v1",
            starts_at=source_bar_end_at,
            confirmed_at=source_bar_end_at,
            source_bar_end_at=source_bar_end_at,
        )


def test_virtual_account_carries_account_bound_execution_context() -> None:
    execution_venue_id = uuid4()
    instrument_id = uuid4()
    account = VirtualAccount(
        id=uuid4(),
        user_id=uuid4(),
        name="Kuveyt Turk paper account",
        base_currency_code="try",
        execution_venue_id=execution_venue_id,
        allowed_execution_instrument_ids=(instrument_id,),
        starting_balance=Money(amount="10000", currency_code="TRY"),
    )

    assert account.execution_venue_id == execution_venue_id
    assert account.allowed_execution_instrument_ids == (instrument_id,)
    assert account.base_currency_code == "TRY"

    with pytest.raises(ValidationError):
        VirtualAccount(
            id=uuid4(),
            user_id=uuid4(),
            name="No instruments",
            base_currency_code="TRY",
            execution_venue_id=execution_venue_id,
            allowed_execution_instrument_ids=(),
            starting_balance=Money(amount="10000", currency_code="TRY"),
        )
