from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from silverpilot.app.domain import (
    BacktestDatasetSnapshot,
    BacktestRun,
    BankInstrument,
    Currency,
    IndicatorSnapshot,
    LedgerEntry,
    MarketBar,
    MarketRegimeSnapshot,
    Money,
    PaperOrder,
    PaperTrade,
    Position,
    PriceQuote,
    Quantity,
    RiskDecision,
    StrategyDefinition,
    StrategyRun,
    TradeIntent,
    Unit,
    VirtualAccount,
)
from silverpilot.app.domain.enums import (
    BacktestRunStatus,
    InstrumentType,
    MarketRegime,
    PaperOrderSide,
    PaperOrderStatus,
    RiskDecisionOutcome,
    StrategyRunStatus,
    TradeIntentSide,
    TradeIntentStatus,
)


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


def test_strategy_run_and_trade_intent_validation() -> None:
    source_bar_end_at = datetime(2026, 6, 17, 11, 0, tzinfo=UTC)
    strategy = StrategyDefinition(
        id=uuid4(),
        name=" trend_up_pullback ",
        version="1",
        parameters={"cash_amount": "1000"},
    )
    run = StrategyRun(
        id=uuid4(),
        strategy_id=strategy.id,
        account_id=uuid4(),
        instrument_type=InstrumentType.REFERENCE,
        instrument_id=uuid4(),
        source="reference-fixture",
        timeframe="1h",
        source_bar_end_at=source_bar_end_at,
        run_at=source_bar_end_at + timedelta(minutes=1),
        input_hash="abc",
        status=StrategyRunStatus.INTENT_CREATED,
        evidence={},
    )
    intent = TradeIntent(
        id=uuid4(),
        account_id=run.account_id,
        strategy_run_id=run.id,
        side=TradeIntentSide.BUY,
        cash_amount="1000",
        signal_time=run.run_at,
        status=TradeIntentStatus.PENDING_RISK,
        rationale="trend_up_pullback_long",
        evidence={},
    )

    assert strategy.name == "trend_up_pullback"
    assert run.status == StrategyRunStatus.INTENT_CREATED
    assert intent.cash_amount == Decimal("1000")

    with pytest.raises(ValidationError):
        TradeIntent(
            id=uuid4(),
            account_id=run.account_id,
            strategy_run_id=run.id,
            side=TradeIntentSide.BUY,
            cash_amount="0",
            signal_time=run.run_at,
            status=TradeIntentStatus.PENDING_RISK,
            rationale="trend_up_pullback_long",
            evidence={},
        )


def test_risk_decision_validation() -> None:
    evaluated_at = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)
    decision = RiskDecision(
        id=uuid4(),
        trade_intent_id=uuid4(),
        execution_instrument_id=uuid4(),
        decision=RiskDecisionOutcome.APPROVE,
        requested_cash_amount="500",
        approved_cash_amount="500",
        approved_quantity="10",
        policy_version="risk-v1",
        reasons=["risk_approved"],
        constraints_applied={"spread_pct": "0.02"},
        evaluated_at=evaluated_at,
    )

    assert decision.decision == RiskDecisionOutcome.APPROVE
    assert decision.execution_instrument_id is not None
    assert decision.approved_cash_amount == Decimal("500")

    with pytest.raises(ValidationError):
        RiskDecision(
            id=uuid4(),
            trade_intent_id=uuid4(),
            decision=RiskDecisionOutcome.APPROVE,
            requested_cash_amount="500",
            approved_cash_amount=None,
            approved_quantity=None,
            policy_version="risk-v1",
            reasons=["risk_approved"],
            constraints_applied={},
            evaluated_at=evaluated_at,
        )


def test_paper_trading_domain_models_validation() -> None:
    executed_at = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)
    order = PaperOrder(
        id=uuid4(),
        account_id=uuid4(),
        trade_intent_id=uuid4(),
        risk_decision_id=uuid4(),
        execution_instrument_id=uuid4(),
        bank_instrument_id=uuid4(),
        side=PaperOrderSide.BUY,
        requested_quantity="10",
        approved_quantity="10",
        status=PaperOrderStatus.EXECUTED,
    )
    trade = PaperTrade(
        id=uuid4(),
        order_id=order.id,
        account_id=order.account_id,
        execution_instrument_id=order.execution_instrument_id,
        bank_instrument_id=order.bank_instrument_id,
        quote_id=uuid4(),
        side=PaperOrderSide.BUY,
        quantity="10",
        execution_price="50",
        gross_cash_amount="500",
        fees="0.5",
        taxes="0",
        spread_cost="10",
        net_cash_amount="500.5",
        realized_pnl="0",
        executed_at=executed_at,
    )
    position = Position(
        id=uuid4(),
        account_id=order.account_id,
        bank_instrument_id=order.bank_instrument_id,
        quantity="10",
        average_cost="50.05",
        realized_pnl="0",
    )
    ledger = LedgerEntry(
        id=uuid4(),
        account_id=order.account_id,
        currency_id=uuid4(),
        amount="-500.5",
        entry_type="paper_buy_cash",
        reference_type="paper_trade",
        reference_id=trade.id,
        metadata_json={"order_id": str(order.id)},
    )

    assert order.side == PaperOrderSide.BUY
    assert trade.net_cash_amount == Decimal("500.5")
    assert position.average_cost == Decimal("50.05")
    assert ledger.amount == Decimal("-500.5")

    with pytest.raises(ValidationError):
        PaperOrder(
            id=uuid4(),
            account_id=uuid4(),
            trade_intent_id=uuid4(),
            risk_decision_id=uuid4(),
            execution_instrument_id=uuid4(),
            bank_instrument_id=uuid4(),
            side=PaperOrderSide.SELL,
            requested_quantity="0",
            approved_quantity="10",
            status=PaperOrderStatus.PENDING,
        )


def test_backtest_domain_models_validation() -> None:
    started_at = datetime(2026, 6, 18, 1, 0, tzinfo=UTC)
    completed_at = started_at + timedelta(hours=3)
    snapshot = BacktestDatasetSnapshot(
        id=uuid4(),
        instrument_type=InstrumentType.REFERENCE,
        instrument_id=uuid4(),
        execution_instrument_id=uuid4(),
        source="reference-fixture",
        timeframe="1h",
        quote_source="kuveyt_turk_finance_portal",
        start_at=started_at,
        end_at=completed_at,
        input_ranges={"quotes": [{"id": "quote-1"}]},
        data_hash="abc",
    )
    run = BacktestRun(
        id=uuid4(),
        dataset_snapshot_id=snapshot.id,
        account_id=uuid4(),
        strategy_id=uuid4(),
        config_hash="def",
        status=BacktestRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        report_json={"pnl_after_costs": "10.00"},
    )

    assert snapshot.data_hash == "abc"
    assert run.status == BacktestRunStatus.COMPLETED

    with pytest.raises(ValidationError):
        BacktestDatasetSnapshot(
            id=uuid4(),
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=uuid4(),
            execution_instrument_id=uuid4(),
            source="reference-fixture",
            timeframe="1h",
            quote_source="kuveyt_turk_finance_portal",
            start_at=completed_at,
            end_at=started_at,
            input_ranges={"quotes": []},
            data_hash="abc",
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
