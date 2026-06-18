from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    BankModel,
    CurrencyModel,
    ExecutionVenueModel,
    IndicatorSnapshotModel,
    LedgerEntryModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
    MetalModel,
    PaperOrderModel,
    PaperTradeModel,
    PositionModel,
    StrategyModel,
    StrategyRunModel,
    TradeIntentModel,
    UnitModel,
    UserModel,
    VirtualAccountModel,
)
from silverpilot.app.domain.enums import InstrumentType, MarketRegime, StrategyRunStatus
from silverpilot.app.indicators.service import hash_parameters
from silverpilot.app.strategies import StrategyEngine

SOURCE = "reference-fixture"
TIMEFRAME = "1h"


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def test_strategy_engine_generates_long_intent_for_trend_up_pullback(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        account_id = _add_account(session)
        strategy_id = _add_strategy(session, cash_amount="750")
        _add_market_context(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=source_bar_end_at,
            regime=MarketRegime.TREND_UP,
            close=Decimal("101"),
            ema_50=Decimal("100"),
            ema_200=Decimal("95"),
            rsi_14=Decimal("45"),
            atr_14=Decimal("1.2"),
        )

        result = StrategyEngine(session=session).run(
            strategy_id=strategy_id,
            account_id=account_id,
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            run_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert result.run.status == StrategyRunStatus.INTENT_CREATED.value
        assert len(result.intents) == 1
        assert result.intents[0].side == "buy"
        assert result.intents[0].cash_amount == Decimal("750.00000000")
        assert result.intents[0].status == "pending_risk"
        assert result.intents[0].quantity is None
        assert result.run.evidence["reasons"] == ["trend_up_pullback_confirmed"]


def test_strategy_engine_matches_indicators_by_parameters_hash(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        account_id = _add_account(session)
        strategy_id = _add_strategy(session)
        _add_market_context(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=source_bar_end_at,
            regime=MarketRegime.TREND_UP,
        )
        ema_50 = session.scalar(
            select(IndicatorSnapshotModel).where(
                IndicatorSnapshotModel.instrument_id == instrument_id,
                IndicatorSnapshotModel.indicator_name == "ema",
                IndicatorSnapshotModel.parameters_hash == hash_parameters({"period": 50}),
            )
        )
        assert ema_50 is not None
        ema_50.parameters = {"period": "50"}

        result = StrategyEngine(session=session).run(
            strategy_id=strategy_id,
            account_id=account_id,
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            run_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert result.run.status == StrategyRunStatus.INTENT_CREATED.value
        assert result.run.evidence["reasons"] == ["trend_up_pullback_confirmed"]


@pytest.mark.parametrize(
    "regime",
    [
        MarketRegime.TREND_DOWN,
        MarketRegime.RANGE,
        MarketRegime.HIGH_VOLATILITY,
        MarketRegime.LOW_VOLATILITY,
        MarketRegime.NO_TRADE,
    ],
)
def test_strategy_engine_emits_no_intent_outside_trend_up(
    engine: Engine,
    regime: MarketRegime,
) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        account_id = _add_account(session)
        strategy_id = _add_strategy(session)
        _add_market_context(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=source_bar_end_at,
            regime=regime,
        )

        result = StrategyEngine(session=session).run(
            strategy_id=strategy_id,
            account_id=account_id,
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            run_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert result.run.status == StrategyRunStatus.NO_INTENT.value
        assert result.intents == []
        assert result.run.evidence["reasons"] == [f"regime_blocked:{regime.value}"]


def test_strategy_engine_emits_no_intent_for_missing_or_stale_data(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        account_id = _add_account(session)
        strategy_id = _add_strategy(session)
        _add_bar(session, instrument_id=instrument_id, source_bar_end_at=source_bar_end_at)
        _add_regime(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=source_bar_end_at,
            regime=MarketRegime.TREND_UP,
        )

        missing = StrategyEngine(session=session).run(
            strategy_id=strategy_id,
            account_id=account_id,
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            run_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert missing.run.status == StrategyRunStatus.NO_INTENT.value
        assert missing.run.evidence["reasons"] == ["missing_indicators"]

    stale_instrument_id = uuid4()
    stale_bar_end_at = _time(3)
    with Session(engine) as session:
        account_id = _add_account(session)
        strategy_id = _add_strategy(session)
        _add_market_context(
            session,
            instrument_id=stale_instrument_id,
            source_bar_end_at=stale_bar_end_at,
            regime=MarketRegime.TREND_UP,
        )

        stale = StrategyEngine(session=session).run(
            strategy_id=strategy_id,
            account_id=account_id,
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=stale_instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=stale_bar_end_at,
            run_at=stale_bar_end_at + timedelta(hours=3),
        )

        assert stale.run.status == StrategyRunStatus.NO_INTENT.value
        assert stale.run.evidence["reasons"] == ["stale_bar"]


def test_strategy_engine_records_no_intent_when_pullback_rules_fail(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        account_id = _add_account(session)
        strategy_id = _add_strategy(session)
        _add_market_context(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=source_bar_end_at,
            regime=MarketRegime.TREND_UP,
            close=Decimal("110"),
            ema_50=Decimal("100"),
            ema_200=Decimal("95"),
        )

        result = StrategyEngine(session=session).run(
            strategy_id=strategy_id,
            account_id=account_id,
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            run_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert result.run.status == StrategyRunStatus.NO_INTENT.value
        assert result.intents == []
        assert result.run.evidence["reasons"] == ["price_not_in_pullback_zone"]


def test_strategy_engine_persists_runs_without_execution_tables(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        account_id = _add_account(session)
        strategy_id = _add_strategy(session)
        _add_market_context(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=source_bar_end_at,
            regime=MarketRegime.TREND_UP,
        )

        StrategyEngine(session=session).run(
            strategy_id=strategy_id,
            account_id=account_id,
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            run_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert session.scalar(select(StrategyRunModel)) is not None
        intent = session.scalar(select(TradeIntentModel))
        assert intent is not None
        assert intent.side == "buy"
        assert session.scalar(select(PaperOrderModel)) is None
        assert session.scalar(select(PaperTradeModel)) is None
        assert session.scalar(select(PositionModel)) is None
        assert session.scalar(select(LedgerEntryModel)) is None


def _add_account(session: Session) -> UUID:
    created_at = _time(0)
    currency = CurrencyModel(
        id=uuid4(),
        code=f"T{len(session.new)}Y"[:3],
        name="Turkish Lira",
        decimal_places=2,
        created_at=created_at,
    )
    unit = UnitModel(
        id=uuid4(),
        code=f"G{len(session.new)}",
        name="Gram",
        precision=6,
        created_at=created_at,
    )
    metal = MetalModel(
        id=uuid4(),
        code=f"X{len(session.new)}",
        name="Silver",
        default_unit=unit,
        created_at=created_at,
    )
    bank = BankModel(
        id=uuid4(),
        code=f"bank_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        country_code="TR",
        status="active",
        created_at=created_at,
    )
    venue = ExecutionVenueModel(
        id=uuid4(),
        venue_type="bank",
        bank=bank,
        code=f"venue_{uuid4().hex[:8]}",
        name="Kuveyt Turk",
        status="active",
        created_at=created_at,
    )
    user = UserModel(
        id=uuid4(),
        email=f"{uuid4().hex[:8]}@example.com",
        status="active",
        created_at=created_at,
    )
    account = VirtualAccountModel(
        id=uuid4(),
        user=user,
        name="Paper account",
        base_currency=currency,
        execution_venue=venue,
        starting_balance=Decimal("10000"),
        status="active",
        created_at=created_at,
    )
    session.add_all([metal, account])
    session.flush()
    return account.id


def _add_strategy(session: Session, *, cash_amount: str = "1000") -> UUID:
    strategy = StrategyModel(
        id=uuid4(),
        name="trend_up_pullback",
        version=uuid4().hex[:8],
        parameters={"cash_amount": cash_amount},
        enabled=True,
        created_at=_time(0),
    )
    session.add(strategy)
    session.flush()
    return strategy.id


def _add_market_context(
    session: Session,
    *,
    instrument_id: UUID,
    source_bar_end_at: datetime,
    regime: MarketRegime,
    close: Decimal = Decimal("101"),
    ema_50: Decimal = Decimal("100"),
    ema_200: Decimal = Decimal("95"),
    rsi_14: Decimal = Decimal("45"),
    atr_14: Decimal = Decimal("1.2"),
) -> None:
    _add_bar(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=source_bar_end_at,
        close=close,
    )
    _add_regime(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=source_bar_end_at,
        regime=regime,
    )
    _add_indicator(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=source_bar_end_at,
        indicator_name="ema",
        parameters={"period": 50},
        value=ema_50,
    )
    _add_indicator(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=source_bar_end_at,
        indicator_name="ema",
        parameters={"period": 200},
        value=ema_200,
    )
    _add_indicator(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=source_bar_end_at,
        indicator_name="rsi",
        parameters={"period": 14},
        value=rsi_14,
    )
    _add_indicator(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=source_bar_end_at,
        indicator_name="atr",
        parameters={"period": 14},
        value=atr_14,
    )


def _add_bar(
    session: Session,
    *,
    instrument_id: UUID,
    source_bar_end_at: datetime,
    close: Decimal = Decimal("101"),
) -> None:
    session.add(
        MarketBarModel(
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            open=Decimal("100"),
            high=max(Decimal("102"), close),
            low=Decimal("99"),
            close=close,
            quote_count=1,
            bar_start_at=source_bar_end_at - timedelta(hours=1),
            bar_end_at=source_bar_end_at,
            created_at=source_bar_end_at,
        )
    )


def _add_regime(
    session: Session,
    *,
    instrument_id: UUID,
    source_bar_end_at: datetime,
    regime: MarketRegime,
) -> None:
    session.add(
        MarketRegimeSnapshotModel(
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            regime=regime.value,
            confidence=Decimal("0.85"),
            evidence={"candidate_regime": regime.value},
            config_version="rule-v1",
            starts_at=source_bar_end_at,
            confirmed_at=source_bar_end_at,
            source_bar_end_at=source_bar_end_at,
            created_at=source_bar_end_at,
        )
    )


def _add_indicator(
    session: Session,
    *,
    instrument_id: UUID,
    source_bar_end_at: datetime,
    indicator_name: str,
    parameters: dict[str, object],
    value: Decimal,
    stored_parameters: dict[str, object] | None = None,
) -> None:
    session.add(
        IndicatorSnapshotModel(
            instrument_type=InstrumentType.REFERENCE.value,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            indicator_name=indicator_name,
            parameters_hash=hash_parameters(parameters),
            parameters=stored_parameters or parameters,
            value=value,
            calculated_at=source_bar_end_at,
            source_bar_end_at=source_bar_end_at,
            created_at=source_bar_end_at,
        )
    )


def _time(hour: int) -> datetime:
    return datetime(2026, 6, 18, hour, 0, tzinfo=UTC)
