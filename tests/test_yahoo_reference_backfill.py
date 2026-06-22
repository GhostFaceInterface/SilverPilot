import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from silverpilot.app.collectors.reference_backfill import backfill_reference_bars
from silverpilot.app.collectors.reference_backfill_cli import (
    CONSERVATIVE_YAHOO_DELAY_SECONDS,
    _blocked_reason,
    _effective_delay_seconds,
)
from silverpilot.app.collectors.reference_backfill_cli import (
    main as reference_backfill_main,
)
from silverpilot.app.db.base import Base
from silverpilot.app.db.models import (
    CurrencyModel,
    MarketBarModel,
    MetalModel,
    ReferenceDataBackfillRunModel,
    ReferenceMarketInstrumentModel,
    SystemHealthEventModel,
    UnitModel,
)
from silverpilot.app.domain.enums import DataQualityStatus, InstrumentType, MarketSessionStatus
from silverpilot.app.domain.models import MarketBar
from silverpilot.app.providers.errors import ProviderParseError
from silverpilot.app.providers.yahoo_finance import (
    YAHOO_RESEARCH_SOURCE_NAME,
    parse_yahoo_chart_payload,
)


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def test_yahoo_chart_parser_aggregates_one_hour_payload_to_four_hour_bars() -> None:
    instrument_id = uuid4()
    fetched_at = datetime(2026, 6, 17, 4, 20, tzinfo=UTC)

    result = parse_yahoo_chart_payload(
        _yahoo_payload([10, 11, 12, 13], [100, 110, 120, 130]),
        instrument_id=instrument_id,
        source=YAHOO_RESEARCH_SOURCE_NAME,
        requested_timeframe="4h",
        provider_interval="1h",
        fetched_at=fetched_at,
        data_delay_seconds=900,
        ingestion_delay_seconds=60,
    )

    assert len(result.bars) == 1
    bar = result.bars[0]
    assert bar.instrument_type == InstrumentType.REFERENCE
    assert bar.instrument_id == instrument_id
    assert bar.source == YAHOO_RESEARCH_SOURCE_NAME
    assert bar.timeframe == "4h"
    assert bar.open == Decimal("10")
    assert bar.high == Decimal("13.5")
    assert bar.low == Decimal("9.5")
    assert bar.close == Decimal("13")
    assert bar.quote_count == 4
    assert bar.volume == Decimal("460")
    assert bar.bar_start_at == datetime(2026, 6, 17, 0, 0, tzinfo=UTC)
    assert bar.bar_end_at == datetime(2026, 6, 17, 4, 0, tzinfo=UTC)
    assert bar.signal_available_at == datetime(2026, 6, 17, 4, 16, tzinfo=UTC)
    assert len(result.source_hash) == 64
    assert result.provider_interval == "1h"
    assert result.normalized_timeframe == "4h"
    assert result.raw_bar_count == 4
    assert result.dropped_partial_groups == 0


def test_yahoo_chart_parser_drops_unclosed_provider_bars() -> None:
    result = parse_yahoo_chart_payload(
        _yahoo_payload([10, 11, 12], [100, 110, 120]),
        instrument_id=uuid4(),
        source=YAHOO_RESEARCH_SOURCE_NAME,
        requested_timeframe="1h",
        provider_interval="1h",
        fetched_at=datetime(2026, 6, 17, 2, 30, tzinfo=UTC),
        data_delay_seconds=900,
        ingestion_delay_seconds=60,
    )

    assert len(result.bars) == 2
    assert result.bars[-1].bar_end_at == datetime(2026, 6, 17, 2, 0, tzinfo=UTC)
    assert result.raw_bar_count == 2


def test_yahoo_chart_parser_rejects_mismatched_ohlc_arrays() -> None:
    payload = _chart_document([10, 11], [100, 110])
    chart = cast(dict[str, Any], payload["chart"])
    result = cast(list[dict[str, Any]], chart["result"])[0]
    indicators = cast(dict[str, Any], result["indicators"])
    quote = cast(list[dict[str, Any]], indicators["quote"])[0]
    quote["close"] = [10]

    with pytest.raises(ProviderParseError, match="mismatched"):
        parse_yahoo_chart_payload(
            json.dumps(payload),
            instrument_id=uuid4(),
            source=YAHOO_RESEARCH_SOURCE_NAME,
            requested_timeframe="1h",
            provider_interval="1h",
            fetched_at=datetime(2026, 6, 17, 4, 20, tzinfo=UTC),
            data_delay_seconds=900,
            ingestion_delay_seconds=60,
        )


def test_reference_backfill_dry_run_records_audit_without_writing_bars(engine: Engine) -> None:
    instrument_id = uuid4()
    started_at = datetime(2026, 6, 17, 5, 0, tzinfo=UTC)
    with Session(engine) as session:
        instrument = _reference_instrument(instrument_id)
        session.add(instrument)
        session.commit()

        result = backfill_reference_bars(
            session,
            instrument=instrument,
            provider=_FixtureReferenceProvider(_fixture_bars(instrument_id)),
            timeframe="4h",
            period="2y",
            dry_run=True,
            started_at=started_at,
        )
        session.commit()

        assert result.status == "dry_run"
        assert result.bars_fetched == 2
        assert result.rows_inserted == 0
        assert result.rows_updated == 0
        assert result.run.feasibility_summary is not None
        assert result.run.feasibility_summary["bar_count"] == 2
        assert result.run.feasibility_summary["weekend_bar_count"] == 0
        assert result.run.feasibility_summary["repeat_hash_matches_previous"] is None
        assert session.scalar(select(func.count()).select_from(MarketBarModel)) == 0
        assert session.scalar(select(func.count()).select_from(ReferenceDataBackfillRunModel)) == 1


def test_reference_backfill_is_idempotent_for_duplicate_yahoo_bars(engine: Engine) -> None:
    instrument_id = uuid4()
    bars = _fixture_bars(instrument_id)
    with Session(engine) as session:
        instrument = _reference_instrument(instrument_id)
        session.add(instrument)
        session.commit()

        first = backfill_reference_bars(
            session,
            instrument=instrument,
            provider=_FixtureReferenceProvider(bars),
            timeframe="4h",
            period="2y",
            dry_run=False,
            started_at=datetime(2026, 6, 17, 5, 0, tzinfo=UTC),
        )
        second = backfill_reference_bars(
            session,
            instrument=instrument,
            provider=_FixtureReferenceProvider(bars),
            timeframe="4h",
            period="2y",
            dry_run=False,
            started_at=datetime(2026, 6, 17, 5, 5, tzinfo=UTC),
        )
        session.commit()

        assert first.rows_inserted == 2
        assert first.rows_updated == 0
        assert second.rows_inserted == 0
        assert second.rows_updated == 2
        assert first.run.data_hash == second.run.data_hash
        assert second.run.feasibility_summary is not None
        assert second.run.feasibility_summary["repeat_hash_matches_previous"] is True
        assert session.scalar(select(func.count()).select_from(MarketBarModel)) == 2
        assert session.scalar(select(func.count()).select_from(ReferenceDataBackfillRunModel)) == 2


def test_reference_backfill_records_failed_provider_run(engine: Engine) -> None:
    instrument_id = uuid4()
    with Session(engine) as session:
        instrument = _reference_instrument(instrument_id)
        session.add(instrument)
        session.commit()

        result = backfill_reference_bars(
            session,
            instrument=instrument,
            provider=_FailingReferenceProvider(),
            timeframe="4h",
            period="2y",
            dry_run=False,
            started_at=datetime(2026, 6, 17, 5, 0, tzinfo=UTC),
        )
        session.commit()

        assert result.status == "failed"
        assert result.run.error_summary == "reference provider returned no bars"
        assert session.scalar(select(func.count()).select_from(MarketBarModel)) == 0
        assert session.scalar(select(func.count()).select_from(ReferenceDataBackfillRunModel)) == 1
        event = session.scalar(select(SystemHealthEventModel))
        assert event is not None
        assert event.component == "yahoo_research_backfill"
        assert event.status == "degraded"
        assert event.severity == "warning"


def test_reference_backfill_cli_blocks_yahoo_without_instrument(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'reference.db'}"
    db_engine = create_engine(database_url, future=True)
    Base.metadata.create_all(db_engine)

    exit_code = reference_backfill_main(
        [
            "--source",
            YAHOO_RESEARCH_SOURCE_NAME,
            "--symbol",
            "SI=F",
            "--timeframe",
            "4h",
            "--period",
            "2y",
            "--database-url",
            database_url,
            "--dry-run",
        ]
    )

    assert exit_code == 2


def test_reference_backfill_cli_blocks_write_without_reviewed_dry_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'reference.db'}"
    db_engine = create_engine(database_url, future=True)
    Base.metadata.create_all(db_engine)
    with Session(db_engine) as session:
        session.add(_reference_instrument(uuid4()))
        session.commit()

    exit_code = reference_backfill_main(
        [
            "--source",
            YAHOO_RESEARCH_SOURCE_NAME,
            "--symbol",
            "SI=F",
            "--timeframe",
            "4h",
            "--period",
            "2y",
            "--database-url",
            database_url,
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["reason"] == "yahoo_research write backfill requires reviewed dry-run summary id"


def test_yahoo_backfill_gate_requires_owner_accepted_paper_risk() -> None:
    instrument = _reference_instrument(uuid4())
    instrument.source_risk_status = "not_approved"

    reason = _blocked_reason(
        source=YAHOO_RESEARCH_SOURCE_NAME,
        timeframe="4h",
        instrument=instrument,
        data_delay_seconds=None,
    )

    assert reason == "yahoo_research requires source_risk_status=owner_accepted_paper_use_risk"


def test_yahoo_backfill_uses_conservative_delay_when_source_delay_is_assumed() -> None:
    instrument = _reference_instrument(uuid4())
    instrument.data_delay_seconds = None
    instrument.source_delay_status = "assumed_conservative"

    assert _effective_delay_seconds(instrument=instrument, override=None) == (
        CONSERVATIVE_YAHOO_DELAY_SECONDS
    )


class _FixtureReferenceProvider:
    def __init__(self, bars: list[MarketBar]) -> None:
        self._bars = bars

    def fetch_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        period: str,
    ) -> list[MarketBar]:
        assert symbol == "SI=F"
        assert timeframe == "4h"
        assert period == "2y"
        return self._bars


class _FailingReferenceProvider:
    def fetch_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        period: str,
    ) -> list[MarketBar]:
        return []


def _reference_instrument(instrument_id: UUID) -> ReferenceMarketInstrumentModel:
    created_at = datetime(2026, 6, 17, 0, 0, tzinfo=UTC)
    unit = UnitModel(
        id=uuid4(),
        code=f"OZ{uuid4().hex[:4]}",
        name="Troy Ounce",
        precision=6,
        created_at=created_at,
    )
    metal = MetalModel(
        id=uuid4(),
        code=f"X{uuid4().hex[:4]}",
        name="Silver",
        default_unit=unit,
        created_at=created_at,
    )
    currency = CurrencyModel(
        id=uuid4(),
        code=f"C{uuid4().hex[:2]}",
        name="US Dollar",
        decimal_places=2,
        created_at=created_at,
    )
    return ReferenceMarketInstrumentModel(
        id=instrument_id,
        symbol="SI=F",
        source=YAHOO_RESEARCH_SOURCE_NAME,
        metal=metal,
        currency=currency,
        unit=unit,
        status="active",
        provider="yahoo_finance_chart",
        exchange="CMX",
        timezone="America/New_York",
        data_delay_seconds=None,
        delay_policy="manual_review",
        source_delay_status="assumed_conservative",
        session_calendar_code="yahoo-research",
        source_terms_status="not_approved",
        source_risk_status="owner_accepted_paper_use_risk",
        approved_by="owner/manual",
        approved_at=created_at,
        approved_scope="live-paper only",
        approved_symbols="SI=F,TRY=X",
        approved_timeframe="4h",
        real_money_allowed=False,
        created_at=created_at,
    )


def _fixture_bars(instrument_id: UUID) -> list[MarketBar]:
    start = datetime(2026, 6, 17, 0, 0, tzinfo=UTC)
    return [
        _bar(instrument_id, start, Decimal("29.10"), Decimal("29.50")),
        _bar(instrument_id, start + timedelta(hours=4), Decimal("29.50"), Decimal("30.10")),
    ]


def _bar(
    instrument_id: UUID,
    start: datetime,
    open_price: Decimal,
    close_price: Decimal,
) -> MarketBar:
    end = start + timedelta(hours=4)
    return MarketBar(
        id=uuid4(),
        instrument_type=InstrumentType.REFERENCE,
        instrument_id=instrument_id,
        source=YAHOO_RESEARCH_SOURCE_NAME,
        timeframe="4h",
        open=open_price,
        high=max(open_price, close_price) + Decimal("0.20"),
        low=min(open_price, close_price) - Decimal("0.20"),
        close=close_price,
        quote_count=4,
        bar_start_at=start,
        bar_end_at=end,
        provider_reported_at=end,
        fetched_at=end + timedelta(minutes=16),
        data_delay_seconds=900,
        signal_available_at=end + timedelta(minutes=16),
        adjusted_close=close_price,
        volume=Decimal("1000"),
        data_quality_status=DataQualityStatus.OK,
        session_status=MarketSessionStatus.UNKNOWN,
        is_backfilled=True,
    )


def _yahoo_payload(closes: list[int], volumes: list[int]) -> str:
    return json.dumps(_chart_document(closes, volumes))


def _chart_document(closes: list[int], volumes: list[int]) -> dict[str, object]:
    start = datetime(2026, 6, 17, 0, 0, tzinfo=UTC)
    timestamps = [int((start + timedelta(hours=index)).timestamp()) for index in range(len(closes))]
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": "SI=F",
                        "currency": "USD",
                        "exchangeName": "CMX",
                        "timezone": "EDT",
                        "regularMarketTime": timestamps[-1],
                    },
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": closes,
                                "high": [value + 0.5 for value in closes],
                                "low": [value - 0.5 for value in closes],
                                "close": closes,
                                "volume": volumes,
                            }
                        ],
                        "adjclose": [{"adjclose": closes}],
                    },
                }
            ],
            "error": None,
        }
    }
