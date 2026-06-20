from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.db.base import Base
from silverpilot.app.db.models import IndicatorSnapshotModel, MarketBarModel
from silverpilot.app.domain.enums import InstrumentType
from silverpilot.app.indicators import (
    IndicatorInsufficientData,
    IndicatorService,
    calculate_adx,
    calculate_atr,
    calculate_bollinger_band_width,
    calculate_ema,
    calculate_rsi,
)
from silverpilot.app.indicators.calculators import BarLike
from silverpilot.app.indicators.service import IndicatorName, hash_parameters


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def test_indicator_calculators_match_pandas_ta_reference_fixture() -> None:
    bars = cast(Sequence[BarLike], _fixture_bars(uuid4()))

    assert _rounded(calculate_ema(bars, period=14)) == Decimal("49.527366199121")
    assert _rounded(calculate_rsi(bars, period=14)) == Decimal("79.441962744134")
    assert _rounded(calculate_atr(bars, period=14)) == Decimal("1.080126297391")
    assert _rounded(calculate_adx(bars, period=14)) == Decimal("57.880894366349")
    assert _rounded(
        calculate_bollinger_band_width(
            bars,
            period=20,
            standard_deviations=Decimal("2"),
        )
    ) == Decimal("13.718986112081")


def test_indicator_calculators_fail_on_insufficient_warmup() -> None:
    bars = cast(Sequence[BarLike], _fixture_bars(uuid4())[:5])

    with pytest.raises(IndicatorInsufficientData):
        calculate_rsi(bars, period=14)


def test_indicator_service_caches_snapshot_for_closed_bar(engine: Engine) -> None:
    instrument_id = uuid4()
    calculated_at = datetime(2026, 6, 18, 6, 1, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all(_fixture_bars(instrument_id))
        session.commit()

        result = IndicatorService(session=session).calculate_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source="reference-fixture",
            timeframe="1h",
            indicator_name="ema",
            parameters={"period": 14},
            source_bar_end_at=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
            calculated_at=calculated_at,
        )

        assert result.inserted is True
        assert result.snapshot.parameters_hash == hash_parameters({"period": 14})
        assert _rounded(result.snapshot.value) == Decimal("49.527366199121")

        second = IndicatorService(session=session).calculate_and_cache(
            instrument_type=InstrumentType.REFERENCE,
            instrument_id=instrument_id,
            source="reference-fixture",
            timeframe="1h",
            indicator_name="ema",
            parameters={"period": 14},
            source_bar_end_at=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
            calculated_at=calculated_at + timedelta(seconds=1),
        )

        assert second.inserted is False
        snapshots = list(session.scalars(select(IndicatorSnapshotModel)))
        assert len(snapshots) == 1
        assert snapshots[0].updated_at == calculated_at + timedelta(seconds=1)


def test_indicator_service_persists_all_phase_4_indicators(engine: Engine) -> None:
    instrument_id = uuid4()
    source_bar_end_at = datetime(2026, 6, 18, 6, 0, tzinfo=UTC)
    calculated_at = source_bar_end_at + timedelta(minutes=2)
    scenarios: list[tuple[IndicatorName, dict[str, object], Decimal]] = [
        ("ema", {"period": 14}, Decimal("49.527366199121")),
        ("rsi", {"period": 14}, Decimal("79.441962744134")),
        ("atr", {"period": 14}, Decimal("1.080126297391")),
        ("adx", {"period": 14}, Decimal("57.880894366349")),
        (
            "bb_width",
            {"period": 20, "standard_deviations": "2", "ddof": 1},
            Decimal("13.718986112081"),
        ),
    ]

    with Session(engine) as session:
        session.add_all(_fixture_bars(instrument_id))
        session.commit()
        service = IndicatorService(session=session)

        results = [
            service.calculate_and_cache(
                instrument_type=InstrumentType.REFERENCE,
                instrument_id=instrument_id,
                source="reference-fixture",
                timeframe="1h",
                indicator_name=indicator_name,
                parameters=parameters,
                source_bar_end_at=source_bar_end_at,
                calculated_at=calculated_at,
            )
            for indicator_name, parameters, _expected_value in scenarios
        ]

        assert all(result.inserted for result in results)
        snapshots = list(
            session.scalars(
                select(IndicatorSnapshotModel).order_by(IndicatorSnapshotModel.indicator_name)
            )
        )
        assert len(snapshots) == 5

        by_name = {snapshot.indicator_name: snapshot for snapshot in snapshots}
        for indicator_name, parameters, expected_value in scenarios:
            snapshot = by_name[indicator_name]
            assert snapshot.parameters_hash == hash_parameters(parameters)
            assert _same_timestamp(snapshot.source_bar_end_at, source_bar_end_at)
            assert _rounded(snapshot.value) == expected_value


def test_indicator_service_rejects_unavailable_source_bar_end(engine: Engine) -> None:
    instrument_id = uuid4()
    with Session(engine) as session:
        session.add_all(_fixture_bars(instrument_id))
        session.commit()

        with pytest.raises(ValueError, match="available closed bar"):
            IndicatorService(session=session).calculate_and_cache(
                instrument_type=InstrumentType.REFERENCE,
                instrument_id=instrument_id,
                source="reference-fixture",
                timeframe="1h",
                indicator_name="ema",
                parameters={"period": 14},
                source_bar_end_at=datetime(2026, 6, 18, 6, 30, tzinfo=UTC),
                calculated_at=datetime(2026, 6, 18, 7, 0, tzinfo=UTC),
            )


def test_indicator_service_rejects_lookahead_calculation(engine: Engine) -> None:
    instrument_id = uuid4()
    with Session(engine) as session:
        session.add_all(_fixture_bars(instrument_id))
        session.commit()

        with pytest.raises(ValueError, match="cannot be after calculated_at"):
            IndicatorService(session=session).calculate_and_cache(
                instrument_type=InstrumentType.REFERENCE,
                instrument_id=instrument_id,
                source="reference-fixture",
                timeframe="1h",
                indicator_name="ema",
                parameters={"period": 14},
                source_bar_end_at=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
                calculated_at=datetime(2026, 6, 18, 5, 59, tzinfo=UTC),
            )


def test_indicator_service_rejects_delayed_bar_before_signal_available_at(
    engine: Engine,
) -> None:
    instrument_id = uuid4()
    delayed_bars = _fixture_bars(instrument_id)
    delayed_bars[-1].signal_available_at = datetime(2026, 6, 18, 6, 15, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all(delayed_bars)
        session.commit()

        with pytest.raises(ValueError, match="not yet signal-available"):
            IndicatorService(session=session).calculate_and_cache(
                instrument_type=InstrumentType.REFERENCE,
                instrument_id=instrument_id,
                source="reference-fixture",
                timeframe="1h",
                indicator_name="ema",
                parameters={"period": 14},
                source_bar_end_at=datetime(2026, 6, 18, 6, 0, tzinfo=UTC),
                calculated_at=datetime(2026, 6, 18, 6, 14, tzinfo=UTC),
            )


def _fixture_bars(instrument_id: UUID) -> list[MarketBarModel]:
    start = datetime(2026, 6, 17, 0, 0, tzinfo=UTC)
    closes = [
        "44",
        "44.15",
        "43.9",
        "44.35",
        "44.8",
        "45.1",
        "44.7",
        "45.35",
        "45.8",
        "45.5",
        "46.2",
        "46.6",
        "46.1",
        "46.9",
        "47.3",
        "47.0",
        "47.8",
        "48.2",
        "47.9",
        "48.6",
        "49.1",
        "48.7",
        "49.4",
        "49.8",
        "50.2",
        "49.9",
        "50.6",
        "51.0",
        "50.7",
        "51.4",
    ]
    bars: list[MarketBarModel] = []
    for index, close_value in enumerate(closes):
        close = Decimal(close_value)
        bar_start_at = start + timedelta(hours=index)
        bars.append(
            MarketBarModel(
                id=uuid4(),
                instrument_type=InstrumentType.REFERENCE.value,
                instrument_id=instrument_id,
                source="reference-fixture",
                timeframe="1h",
                open=close - Decimal("0.2"),
                high=close + Decimal("0.55"),
                low=close - Decimal("0.45"),
                close=close,
                quote_count=1,
                bar_start_at=bar_start_at,
                bar_end_at=bar_start_at + timedelta(hours=1),
                created_at=bar_start_at + timedelta(hours=1),
            )
        )
    return bars


def _rounded(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000000000001"))


def _same_timestamp(left: datetime, right: datetime) -> bool:
    if left.tzinfo is None or right.tzinfo is None:
        return left.replace(tzinfo=None) == right.replace(tzinfo=None)
    return left == right
