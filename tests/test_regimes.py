from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    IndicatorSnapshotModel,
    MarketBarModel,
    MarketRegimeSnapshotModel,
)
from silverpilot.app.domain.enums import InstrumentType, MarketRegime
from silverpilot.app.indicators.service import hash_parameters
from silverpilot.app.regimes import RegimeDetector, RegimeDetectorConfig

SOURCE = "reference-fixture"
TIMEFRAME = "1h"


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def test_regime_detector_classifies_trend_up(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        _add_bar_with_indicators(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=_time(1),
            ema_50=Decimal("102"),
            ema_200=Decimal("100"),
        )
        _add_bar_with_indicators(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=source_bar_end_at,
            ema_50=Decimal("104"),
            ema_200=Decimal("100"),
            adx_14=Decimal("30"),
        )

        result = RegimeDetector(session=session).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            detected_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert result.inserted is True
        assert result.snapshot.regime == MarketRegime.TREND_UP.value
        assert result.snapshot.evidence["candidate_regime"] == MarketRegime.TREND_UP.value


def test_regime_detector_matches_indicators_by_parameters_hash(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        _add_bar_with_indicators(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=_time(1),
            ema_50=Decimal("102"),
            ema_200=Decimal("100"),
        )
        _add_bar_with_indicators(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=source_bar_end_at,
            ema_50=Decimal("104"),
            ema_200=Decimal("100"),
            adx_14=Decimal("30"),
        )
        ema_50 = session.scalar(
            select(IndicatorSnapshotModel).where(
                IndicatorSnapshotModel.instrument_id == instrument_id,
                IndicatorSnapshotModel.source_bar_end_at == source_bar_end_at,
                IndicatorSnapshotModel.indicator_name == "ema",
                IndicatorSnapshotModel.parameters_hash == hash_parameters({"period": 50}),
            )
        )
        assert ema_50 is not None
        ema_50.parameters = {"period": "50"}

        result = RegimeDetector(session=session).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            detected_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert result.snapshot.regime == MarketRegime.TREND_UP.value
        assert result.snapshot.evidence["candidate_regime"] == MarketRegime.TREND_UP.value


@pytest.mark.parametrize(
    ("ema_50_previous", "ema_50", "ema_200", "adx_14", "atr_14", "bb_width_20", "expected"),
    [
        (
            Decimal("104"),
            Decimal("101"),
            Decimal("103"),
            Decimal("30"),
            Decimal("1.2"),
            Decimal("5"),
            MarketRegime.TREND_DOWN,
        ),
        (
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("15"),
            Decimal("1.2"),
            Decimal("5"),
            MarketRegime.RANGE,
        ),
        (
            Decimal("102"),
            Decimal("104"),
            Decimal("100"),
            Decimal("30"),
            Decimal("3"),
            Decimal("5"),
            MarketRegime.HIGH_VOLATILITY,
        ),
        (
            Decimal("100"),
            Decimal("100.1"),
            Decimal("100"),
            Decimal("18"),
            Decimal("0.5"),
            Decimal("2"),
            MarketRegime.LOW_VOLATILITY,
        ),
    ],
)
def test_regime_detector_classifies_core_regimes(
    engine: Engine,
    ema_50_previous: Decimal,
    ema_50: Decimal,
    ema_200: Decimal,
    adx_14: Decimal,
    atr_14: Decimal,
    bb_width_20: Decimal,
    expected: MarketRegime,
) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        _add_bar_with_indicators(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=_time(1),
            ema_50=ema_50_previous,
            ema_200=ema_200,
        )
        _add_bar_with_indicators(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=source_bar_end_at,
            ema_50=ema_50,
            ema_200=ema_200,
            adx_14=adx_14,
            atr_14=atr_14,
            bb_width_20=bb_width_20,
        )

        result = RegimeDetector(session=session).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            detected_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert result.snapshot.regime == expected.value


def test_regime_detector_emits_no_trade_for_missing_or_stale_data(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        _add_bar(session, instrument_id=instrument_id, source_bar_end_at=source_bar_end_at)

        missing = RegimeDetector(session=session).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            detected_at=source_bar_end_at + timedelta(minutes=1),
        )

        assert missing.snapshot.regime == MarketRegime.NO_TRADE.value
        assert "missing_indicators" in cast(
            list[str],
            missing.snapshot.evidence["candidate_reasons"],
        )

    stale_instrument_id = uuid4()
    stale_bar_end_at = _time(3)
    with Session(engine) as session:
        _add_bar_with_indicators(
            session,
            instrument_id=stale_instrument_id,
            source_bar_end_at=_time(2),
            ema_50=Decimal("100"),
            ema_200=Decimal("99"),
        )
        _add_bar_with_indicators(
            session,
            instrument_id=stale_instrument_id,
            source_bar_end_at=stale_bar_end_at,
            ema_50=Decimal("101"),
            ema_200=Decimal("99"),
        )

        stale = RegimeDetector(session=session).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=stale_instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=stale_bar_end_at,
            detected_at=stale_bar_end_at + timedelta(hours=3),
        )

        assert stale.snapshot.regime == MarketRegime.NO_TRADE.value
        assert "stale_bar" in cast(list[str], stale.snapshot.evidence["candidate_reasons"])


def test_regime_detector_requires_hysteresis_before_switching(engine: Engine) -> None:
    instrument_id = uuid4()
    config = RegimeDetectorConfig(cooldown=timedelta(0), confirmation_bars=2)
    with Session(engine) as session:
        _add_trend_up_input(session, instrument_id=instrument_id, hour=1, ema_50=Decimal("101"))
        _add_trend_up_input(session, instrument_id=instrument_id, hour=2, ema_50=Decimal("103"))
        first = RegimeDetector(session=session, config=config).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=_time(2),
            detected_at=_time(2, minute=1),
        )
        assert first.snapshot.regime == MarketRegime.TREND_UP.value

        _add_trend_down_input(session, instrument_id=instrument_id, hour=3, ema_50=Decimal("99"))
        blocked = RegimeDetector(session=session, config=config).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=_time(3),
            detected_at=_time(3, minute=1),
        )
        assert blocked.snapshot.regime == MarketRegime.TREND_UP.value
        assert blocked.snapshot.evidence["transition_blocked"] == "hysteresis"

        _add_trend_down_input(session, instrument_id=instrument_id, hour=4, ema_50=Decimal("97"))
        switched = RegimeDetector(session=session, config=config).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=_time(4),
            detected_at=_time(4, minute=1),
        )
        assert switched.snapshot.regime == MarketRegime.TREND_DOWN.value
        assert switched.snapshot.evidence["transition_confirmed"] is True


def test_regime_detector_respects_cooldown(engine: Engine) -> None:
    instrument_id = uuid4()
    config = RegimeDetectorConfig(cooldown=timedelta(hours=2), confirmation_bars=1)
    with Session(engine) as session:
        _add_trend_up_input(session, instrument_id=instrument_id, hour=1, ema_50=Decimal("101"))
        _add_trend_up_input(session, instrument_id=instrument_id, hour=2, ema_50=Decimal("103"))
        RegimeDetector(session=session, config=config).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=_time(2),
            detected_at=_time(2, minute=1),
        )

        _add_trend_down_input(session, instrument_id=instrument_id, hour=3, ema_50=Decimal("99"))
        blocked = RegimeDetector(session=session, config=config).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=_time(3),
            detected_at=_time(3, minute=1),
        )

        assert blocked.snapshot.regime == MarketRegime.TREND_UP.value
        assert blocked.snapshot.evidence["transition_blocked"] == "cooldown"


def test_regime_detector_exits_stale_no_trade_when_fresh_data_returns(engine: Engine) -> None:
    instrument_id = uuid4()
    config = RegimeDetectorConfig(cooldown=timedelta(hours=2), confirmation_bars=2)
    with Session(engine) as session:
        _add_bar(session, instrument_id=instrument_id, source_bar_end_at=_time(1))
        stale = RegimeDetector(session=session, config=config).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=_time(1),
            detected_at=_time(4),
        )
        assert stale.snapshot.regime == MarketRegime.NO_TRADE.value

        _add_bar_with_indicators(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=_time(3),
            ema_50=Decimal("101"),
            ema_200=Decimal("100"),
            bb_width_20=Decimal("12"),
        )
        _add_bar_with_indicators(
            session,
            instrument_id=instrument_id,
            source_bar_end_at=_time(4),
            ema_50=Decimal("102"),
            ema_200=Decimal("100"),
            bb_width_20=Decimal("12"),
        )
        fresh = RegimeDetector(session=session, config=config).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=_time(4),
            detected_at=_time(4, minute=1),
        )

        assert fresh.snapshot.regime == MarketRegime.HIGH_VOLATILITY.value
        assert fresh.snapshot.evidence["candidate_regime"] == MarketRegime.HIGH_VOLATILITY.value
        assert fresh.snapshot.evidence["transition_from_no_trade"] is True
        assert "transition_blocked" not in fresh.snapshot.evidence


def test_regime_detector_is_idempotent_for_same_window(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = _time(2)
    with Session(engine) as session:
        _add_trend_up_input(session, instrument_id=instrument_id, hour=1, ema_50=Decimal("101"))
        _add_trend_up_input(session, instrument_id=instrument_id, hour=2, ema_50=Decimal("103"))
        detector = RegimeDetector(session=session)

        first = detector.detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            detected_at=source_bar_end_at + timedelta(minutes=1),
        )
        second = detector.detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=source_bar_end_at,
            detected_at=source_bar_end_at + timedelta(minutes=2),
        )

        snapshots = list(session.scalars(select(MarketRegimeSnapshotModel)))
        assert first.inserted is True
        assert second.inserted is False
        assert len(snapshots) == 1
        assert snapshots[0].updated_at == source_bar_end_at + timedelta(minutes=2)


def test_regime_detector_rejects_lookahead_evaluation(engine: Engine) -> None:
    with Session(engine) as session, pytest.raises(ValueError, match="source_bar_end_at"):
        RegimeDetector(session=session).detect_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=uuid4(),
            source=SOURCE,
            timeframe=TIMEFRAME,
            source_bar_end_at=_time(2),
            detected_at=_time(1),
        )


def _add_trend_up_input(
    session: Session,
    *,
    instrument_id: UUID,
    hour: int,
    ema_50: Decimal,
) -> None:
    _add_bar_with_indicators(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=_time(hour),
        ema_50=ema_50,
        ema_200=Decimal("100"),
        adx_14=Decimal("30"),
    )


def _add_trend_down_input(
    session: Session,
    *,
    instrument_id: UUID,
    hour: int,
    ema_50: Decimal,
) -> None:
    _add_bar_with_indicators(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=_time(hour),
        ema_50=ema_50,
        ema_200=Decimal("100"),
        adx_14=Decimal("30"),
    )


def _add_bar_with_indicators(
    session: Session,
    *,
    instrument_id: UUID,
    source_bar_end_at: datetime,
    ema_50: Decimal,
    ema_200: Decimal,
    adx_14: Decimal = Decimal("30"),
    atr_14: Decimal = Decimal("1.2"),
    bb_width_20: Decimal = Decimal("5"),
) -> None:
    _add_bar(session, instrument_id=instrument_id, source_bar_end_at=source_bar_end_at)
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
        indicator_name="adx",
        parameters={"period": 14},
        value=adx_14,
    )
    _add_indicator(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=source_bar_end_at,
        indicator_name="atr",
        parameters={"period": 14},
        value=atr_14,
    )
    _add_indicator(
        session,
        instrument_id=instrument_id,
        source_bar_end_at=source_bar_end_at,
        indicator_name="bb_width",
        parameters={"period": 20},
        value=bb_width_20,
    )


def _add_bar(session: Session, *, instrument_id: UUID, source_bar_end_at: datetime) -> None:
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
            bar_start_at=source_bar_end_at - timedelta(hours=1),
            bar_end_at=source_bar_end_at,
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


def _time(hour: int, *, minute: int = 0) -> datetime:
    return datetime(2026, 6, 18, hour, minute, tzinfo=UTC)
