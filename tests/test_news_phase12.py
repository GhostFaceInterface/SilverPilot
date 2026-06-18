from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from silverpilot.app.db.base import Base
from silverpilot.app.db.models import EventRiskSnapshotModel, NewsEventModel
from silverpilot.app.news import (
    NewsEventPayload,
    NewsInterpreter,
    NewsRiskRepository,
    NewsSourceDefinition,
)

BASE_TIME = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


@pytest.fixture()
def engine() -> Engine:
    db_engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(db_engine)
    return db_engine


def test_news_interpreter_outputs_hermes_risk_schema_for_fresh_event() -> None:
    interpreter = NewsInterpreter()

    result = interpreter.interpret(
        event=_event(title="Central bank policy shock", summary="A hawkish rate hike surprised."),
        interpreted_at=BASE_TIME,
    )

    assert result is not None
    payload = result.to_payload()
    assert payload["source"] == "tcmb"
    assert payload["affected_assets"] == ["XAG"]
    assert payload["direction_bias"] == "bearish"
    assert payload["risk_level"] == "high"
    assert payload["action_recommendation"] == "no_trade"
    assert payload["schema_version"] == "hermes-risk-v1"


def test_news_interpreter_ignores_stale_news() -> None:
    interpreter = NewsInterpreter()

    result = interpreter.interpret(
        event=_event(
            published_at=BASE_TIME - timedelta(days=2),
            fetched_at=BASE_TIME - timedelta(days=2),
        ),
        interpreted_at=BASE_TIME,
    )

    assert result is None


def test_news_interpreter_rejects_lookahead_news() -> None:
    interpreter = NewsInterpreter()

    with pytest.raises(ValueError, match="before it is available"):
        interpreter.interpret(
            event=_event(fetched_at=BASE_TIME + timedelta(minutes=5)),
            interpreted_at=BASE_TIME,
        )


def test_news_repository_persists_events_and_idempotent_risk_snapshot(engine: Engine) -> None:
    with Session(engine) as session:
        repository = NewsRiskRepository(session=session)
        repository.upsert_source(source=_source(), stored_at=BASE_TIME)
        event = repository.record_event(event=_event(), stored_at=BASE_TIME)

        first = repository.interpret_event(news_event_id=event.id, interpreted_at=BASE_TIME)
        second = repository.interpret_event(
            news_event_id=event.id,
            interpreted_at=BASE_TIME + timedelta(minutes=1),
        )

        assert first is not None
        assert second is not None
        assert first.id == second.id
        stored_event = session.scalar(select(NewsEventModel))
        assert stored_event is not None
        assert stored_event.id == event.id
        snapshots = list(session.scalars(select(EventRiskSnapshotModel)))
        assert len(snapshots) == 1
        assert snapshots[0].action_recommendation == "no_trade"
        assert snapshots[0].payload["action_recommendation"] == "no_trade"


def test_news_repository_does_not_persist_snapshot_for_stale_event(engine: Engine) -> None:
    with Session(engine) as session:
        repository = NewsRiskRepository(session=session)
        repository.upsert_source(source=_source(), stored_at=BASE_TIME)
        event = repository.record_event(
            event=_event(
                published_at=BASE_TIME - timedelta(days=2),
                fetched_at=BASE_TIME - timedelta(days=2),
            ),
            stored_at=BASE_TIME,
        )

        result = repository.interpret_event(news_event_id=event.id, interpreted_at=BASE_TIME)

        assert result is None
        assert session.scalar(select(EventRiskSnapshotModel)) is None


def _source() -> NewsSourceDefinition:
    return NewsSourceDefinition(
        code="tcmb",
        name="TCMB",
        category="central_bank",
        reliability_score=Decimal("0.9000"),
        source_policy="official public source; no trading authority",
    )


def _event(
    *,
    title: str = "Central bank policy shock",
    summary: str = "A hawkish rate hike surprised markets.",
    published_at: datetime = BASE_TIME - timedelta(minutes=2),
    fetched_at: datetime = BASE_TIME - timedelta(minutes=1),
) -> NewsEventPayload:
    return NewsEventPayload(
        source_code="tcmb",
        source_event_time=published_at,
        provider_reported_at=published_at,
        published_at=published_at,
        fetched_at=fetched_at,
        title=title,
        summary=summary,
        affected_assets=("XAG",),
        event_type="central_bank",
    )
