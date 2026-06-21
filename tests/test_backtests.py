from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.backtests import (
    BacktestConfig,
    BacktestDatasetSnapshotService,
    BacktestEngine,
)
from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    BacktestDatasetSnapshotModel,
    BacktestRunModel,
    BankInstrumentModel,
    BankModel,
    CurrencyModel,
    ExecutionInstrumentModel,
    ExecutionVenueModel,
    IndicatorSnapshotModel,
    InstrumentMappingModel,
    LedgerEntryModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    MetalModel,
    PaperOrderModel,
    PaperTradeModel,
    PriceQuoteModel,
    ReferenceMarketInstrumentModel,
    RiskDecisionModel,
    StrategyModel,
    StrategyRunModel,
    TradeIntentModel,
    UnitModel,
    UserModel,
    VirtualAccountInstrumentModel,
    VirtualAccountModel,
    WalletModel,
)
from silverpilot.app.domain.enums import InstrumentType, MarketRegime
from silverpilot.app.indicators.service import hash_parameters
from silverpilot.app.paper_trading import PaperCostModel
from silverpilot.app.risks import RiskPolicy

SOURCE = "reference-fixture"
QUOTE_SOURCE = "kuveyt_turk_finance_portal"
TIMEFRAME = "1h"
START = datetime(2026, 6, 18, 1, 0, tzinfo=UTC)
FIRST_BAR = datetime(2026, 6, 18, 2, 0, tzinfo=UTC)
SECOND_BAR = datetime(2026, 6, 18, 3, 0, tzinfo=UTC)
END = datetime(2026, 6, 18, 4, 0, tzinfo=UTC)


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def test_backtest_engine_replays_deterministically_with_cost_inclusive_report(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        fixture = _seed_backtest_fixture(session)
        config = _config(fixture)

        first = BacktestEngine(session=session).run(config=config)
        second = BacktestEngine(session=session).run(config=config)

        assert first.data_hash == second.data_hash
        assert first.pnl_after_costs == second.pnl_after_costs
        assert first.portfolio_curve[-1].total_value == second.portfolio_curve[-1].total_value
        assert first.trade_count == second.trade_count == 1
        assert first.total_costs == Decimal("10.50000000")
        assert first.pnl_before_costs == Decimal("100.00000000")
        assert first.pnl_after_costs == Decimal("89.50000000")
        assert first.pnl_before_costs != first.pnl_after_costs
        assert first.max_drawdown == Decimal("0.01050000")
        assert first.no_trade_reasons[-1].reasons == ["regime_blocked:range"]
        assert len(first.executed_trades) == 1
        executed = first.executed_trades[0]
        assert executed.signal_source == SOURCE
        assert executed.execution_source == QUOTE_SOURCE
        assert executed.source_bar_end_at == FIRST_BAR
        assert executed.signal_available_at is None
        assert executed.execution_quote_observed_at == FIRST_BAR
        assert executed.quote_lag_seconds == 60
        assert executed.bank_buy_price == Decimal("49.00000000")
        assert executed.bank_sell_price == Decimal("50.00000000")
        assert executed.bank_spread == Decimal("1.00000000")
        assert executed.bank_spread_pct == Decimal("0.02")
        assert executed.execution_price == Decimal("50.00000000")
        assert executed.spread_cost == Decimal("10.00000000")
        assert executed.total_costs == Decimal("10.50000000")
        assert executed.premium_discount_status == "not_calculated_without_approved_fx_source"
        live_wallet = session.get(WalletModel, fixture.live_wallet_id)
        assert live_wallet is not None
        assert live_wallet.available_amount == Decimal("1000.00000000")


def test_backtest_dataset_hash_changes_when_quote_input_changes(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_backtest_fixture(session)
        service = BacktestDatasetSnapshotService(session=session)

        first = service.create(config=_config(fixture)).snapshot
        quote = session.scalar(
            select(PriceQuoteModel).where(PriceQuoteModel.observed_at == SECOND_BAR)
        )
        assert quote is not None
        quote.bank_buy_price = Decimal("58")
        session.flush()
        second = service.create(config=_config(fixture)).snapshot

        assert first.data_hash != second.data_hash
        assert len(list(session.scalars(select(BacktestDatasetSnapshotModel)))) == 2


def test_backtest_replays_delayed_reference_bar_at_signal_available_time(
    engine: Engine,
) -> None:
    signal_available_at = FIRST_BAR + timedelta(minutes=15)
    decision_at = signal_available_at + timedelta(minutes=1)
    with Session(engine) as session:
        fixture = _seed_backtest_fixture(
            session,
            first_signal_available_at=signal_available_at,
        )
        _add_quote(
            session,
            bank_instrument_id=fixture.bank_instrument_id,
            observed_at=decision_at,
            bank_buy=Decimal("54"),
            bank_sell=Decimal("55"),
        )

        report = BacktestEngine(session=session).run(config=_config(fixture))

        strategy_run = session.scalar(
            select(StrategyRunModel).where(StrategyRunModel.account_id == report.account_id)
        )
        assert strategy_run is not None
        assert strategy_run.source_bar_end_at.replace(tzinfo=UTC) == FIRST_BAR
        assert strategy_run.run_at.replace(tzinfo=UTC) == decision_at
        assert report.portfolio_curve[1].timestamp == decision_at
        assert report.trade_count == 1
        assert report.signal_time_policy == "signal_available_at_or_bar_end_at"
        assert report.execution_source == QUOTE_SOURCE
        assert report.executed_trades[0].source_bar_end_at == FIRST_BAR
        assert report.executed_trades[0].signal_available_at == signal_available_at
        assert report.executed_trades[0].evaluated_at == decision_at
        assert report.executed_trades[0].execution_quote_observed_at == decision_at
        assert report.executed_trades[0].quote_lag_seconds == 0
        snapshot = session.get(BacktestDatasetSnapshotModel, report.dataset_snapshot_id)
        assert snapshot is not None
        bars_payload = snapshot.input_ranges["bars"]
        assert isinstance(bars_payload, list)
        first_bar_payload = bars_payload[0]
        assert isinstance(first_bar_payload, dict)
        assert first_bar_payload["signal_available_at"] == signal_available_at.isoformat()


def test_backtest_report_includes_rejected_trades_without_live_account_mutation(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        fixture = _seed_backtest_fixture(
            session,
            first_bank_buy=Decimal("40"),
            first_bank_sell=Decimal("50"),
        )

        report = BacktestEngine(session=session).run(config=_config(fixture))

        assert report.trade_count == 0
        assert report.rejected_trades[0].reasons == ["spread_above_threshold"]
        assert session.scalar(select(PaperTradeModel)) is None
        live_wallet = session.get(WalletModel, fixture.live_wallet_id)
        assert live_wallet is not None
        assert live_wallet.available_amount == Decimal("1000.00000000")


def test_backtest_persists_run_report_and_uses_shared_execution_tables(engine: Engine) -> None:
    with Session(engine) as session:
        fixture = _seed_backtest_fixture(session)

        report = BacktestEngine(session=session).run(config=_config(fixture))

        run = session.scalar(select(BacktestRunModel))
        assert run is not None
        assert run.report_json["data_hash"] == report.data_hash
        assert run.report_json["signal_source"] == SOURCE
        assert run.report_json["execution_source"] == QUOTE_SOURCE
        assert run.report_json["signal_time_policy"] == "signal_available_at_or_bar_end_at"
        executed_trades = cast(list[dict[str, object]], run.report_json["executed_trades"])
        executed_trade = executed_trades[0]
        assert executed_trade["signal_source"] == SOURCE
        assert executed_trade["execution_source"] == QUOTE_SOURCE
        assert executed_trade["execution_quote_observed_at"] == FIRST_BAR.isoformat()
        assert executed_trade["bank_spread_pct"] == "0.02"
        assert executed_trade["total_costs"] == "10.50000000"
        assert session.scalar(select(StrategyRunModel)) is not None
        assert session.scalar(select(TradeIntentModel)) is not None
        assert session.scalar(select(RiskDecisionModel)) is not None
        assert session.scalar(select(PaperOrderModel)) is not None
        assert session.scalar(select(PaperTradeModel)) is not None
        assert len(list(session.scalars(select(LedgerEntryModel)))) == 2


@dataclass(frozen=True)
class _BacktestFixture:
    account_id: UUID
    live_wallet_id: UUID
    strategy_id: UUID
    reference_instrument_id: UUID
    execution_instrument_id: UUID
    bank_instrument_id: UUID


def _config(fixture: _BacktestFixture) -> BacktestConfig:
    return BacktestConfig(
        strategy_id=fixture.strategy_id,
        base_account_id=fixture.account_id,
        execution_instrument_id=fixture.execution_instrument_id,
        instrument_type=InstrumentType.REFERENCE,
        instrument_id=fixture.reference_instrument_id,
        source=SOURCE,
        timeframe=TIMEFRAME,
        quote_source=QUOTE_SOURCE,
        start_at=START,
        end_at=END,
        initial_cash=Decimal("1000"),
        risk_policy=RiskPolicy(
            version="risk-backtest-v1",
            max_position_cash=Decimal("5000"),
            max_order_cash=Decimal("1000"),
            max_daily_loss=Decimal("250"),
            max_drawdown=Decimal("0.50"),
            min_quote_freshness=timedelta(minutes=5),
            max_spread_pct=Decimal("0.03"),
            min_order_cash=Decimal("100"),
            min_expected_edge_after_costs=Decimal("0"),
        ),
        cost_model=PaperCostModel(fee_rate=Decimal("0.001"), tax_rate=Decimal("0")),
    )


def _seed_backtest_fixture(
    session: Session,
    *,
    first_bank_buy: Decimal = Decimal("49"),
    first_bank_sell: Decimal = Decimal("50"),
    first_signal_available_at: datetime | None = None,
) -> _BacktestFixture:
    currency = CurrencyModel(
        id=uuid4(),
        code=f"T{uuid4().hex[:2]}",
        name="Turkish Lira",
        decimal_places=2,
        created_at=START,
    )
    unit = UnitModel(
        id=uuid4(), code=f"G{uuid4().hex[:4]}", name="Gram", precision=6, created_at=START
    )
    metal = MetalModel(
        id=uuid4(), code=f"X{uuid4().hex[:4]}", name="Silver", default_unit=unit, created_at=START
    )
    bank = BankModel(
        id=uuid4(),
        code=f"bank_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        country_code="TR",
        status="active",
        created_at=START,
    )
    venue = ExecutionVenueModel(
        id=uuid4(),
        venue_type="bank",
        bank=bank,
        code=f"venue_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        status="active",
        created_at=START,
    )
    bank_instrument = BankInstrumentModel(
        id=uuid4(),
        bank=bank,
        metal=metal,
        currency=currency,
        unit=unit,
        symbol=f"KT-XAG-{uuid4().hex[:6]}",
        min_trade_amount=Decimal("100"),
        quantity_precision=4,
        price_precision=4,
        status="active",
        created_at=START,
    )
    execution_instrument = ExecutionInstrumentModel(
        id=uuid4(),
        execution_venue=venue,
        bank_instrument=bank_instrument,
        metal=metal,
        currency=currency,
        unit=unit,
        symbol=f"KT-XAG-{uuid4().hex[:6]}",
        status="active",
        created_at=START,
    )
    reference = ReferenceMarketInstrumentModel(
        id=uuid4(),
        symbol=f"REF-XAG-{uuid4().hex[:6]}",
        source=SOURCE,
        metal=metal,
        currency=currency,
        unit=unit,
        status="active",
        created_at=START,
    )
    mapping = InstrumentMappingModel(
        id=uuid4(),
        reference_market_instrument=reference,
        execution_instrument=execution_instrument,
        status="active",
        created_at=START,
    )
    user = UserModel(
        id=uuid4(), email=f"{uuid4().hex[:8]}@example.com", status="active", created_at=START
    )
    account = VirtualAccountModel(
        id=uuid4(),
        user=user,
        name="Live paper account",
        base_currency=currency,
        execution_venue=venue,
        starting_balance=Decimal("1000"),
        status="active",
        created_at=START,
    )
    wallet = WalletModel(
        id=uuid4(),
        virtual_account=account,
        currency=currency,
        available_amount=Decimal("1000"),
        reserved_amount=Decimal("0"),
        created_at=START,
    )
    allowed = VirtualAccountInstrumentModel(
        id=uuid4(),
        virtual_account=account,
        execution_instrument=execution_instrument,
        status="active",
        created_at=START,
    )
    strategy = StrategyModel(
        id=uuid4(),
        name="trend_up_pullback",
        version=uuid4().hex[:8],
        parameters={"cash_amount": "500"},
        enabled=True,
        created_at=START,
    )
    session.add_all([mapping, wallet, allowed, strategy])
    _add_market_context(
        session,
        reference.id,
        FIRST_BAR,
        MarketRegime.TREND_UP,
        signal_available_at=first_signal_available_at,
    )
    _add_market_context(session, reference.id, SECOND_BAR, MarketRegime.RANGE)
    _add_quote(
        session,
        bank_instrument_id=bank_instrument.id,
        observed_at=FIRST_BAR,
        bank_buy=first_bank_buy,
        bank_sell=first_bank_sell,
    )
    _add_quote(
        session,
        bank_instrument_id=bank_instrument.id,
        observed_at=SECOND_BAR,
        bank_buy=Decimal("59"),
        bank_sell=Decimal("60"),
    )
    session.flush()
    return _BacktestFixture(
        account_id=account.id,
        live_wallet_id=wallet.id,
        strategy_id=strategy.id,
        reference_instrument_id=reference.id,
        execution_instrument_id=execution_instrument.id,
        bank_instrument_id=bank_instrument.id,
    )


def _add_market_context(
    session: Session,
    instrument_id: UUID,
    bar_end_at: datetime,
    regime: MarketRegime,
    *,
    signal_available_at: datetime | None = None,
) -> None:
    session.add(
        MarketBarModel(
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            quote_count=1,
            bar_start_at=bar_end_at - timedelta(hours=1),
            bar_end_at=bar_end_at,
            data_delay_seconds=(
                int((signal_available_at - bar_end_at).total_seconds())
                if signal_available_at is not None
                else None
            ),
            signal_available_at=signal_available_at,
            created_at=bar_end_at,
        )
    )
    session.add(
        MarketRegimeSnapshotModel(
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            regime=regime.value,
            confidence=Decimal("0.8500"),
            evidence={"candidate_regime": regime.value},
            config_version="rule-v1",
            starts_at=bar_end_at,
            confirmed_at=bar_end_at,
            source_bar_end_at=bar_end_at,
            created_at=bar_end_at,
        )
    )
    indicator_inputs: tuple[tuple[str, dict[str, object], Decimal], ...] = (
        ("ema", {"period": 50}, Decimal("100")),
        ("ema", {"period": 200}, Decimal("95")),
        ("rsi", {"period": 14}, Decimal("45")),
        ("atr", {"period": 14}, Decimal("1.2")),
    )
    for indicator_name, parameters, value in indicator_inputs:
        session.add(
            IndicatorSnapshotModel(
                instrument_type=InstrumentType.REFERENCE.value,
                instrument_id=instrument_id,
                source=SOURCE,
                timeframe=TIMEFRAME,
                indicator_name=indicator_name,
                parameters_hash=hash_parameters(parameters),
                parameters=parameters,
                value=value,
                calculated_at=bar_end_at,
                source_bar_end_at=bar_end_at,
                created_at=bar_end_at,
            )
        )


def _add_quote(
    session: Session,
    *,
    bank_instrument_id: UUID,
    observed_at: datetime,
    bank_buy: Decimal,
    bank_sell: Decimal,
) -> None:
    session.add(
        PriceQuoteModel(
            id=uuid4(),
            bank_instrument_id=bank_instrument_id,
            bank_buy_price=bank_buy,
            bank_sell_price=bank_sell,
            observed_at=observed_at,
            fetched_at=observed_at,
            source=QUOTE_SOURCE,
            source_hash=f"quote-{observed_at.isoformat()}",
            freshness_status="fresh",
            created_at=observed_at,
        )
    )
