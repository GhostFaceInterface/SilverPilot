import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from silverpilot.app.db.models import (
    FxReferenceInstrumentModel,
    MarketBarModel,
    ReferenceDataBackfillRunModel,
    ReferenceMarketInstrumentModel,
    SystemHealthEventModel,
)
from silverpilot.app.domain.enums import InstrumentType
from silverpilot.app.domain.interfaces import ReferenceMarketDataProvider
from silverpilot.app.domain.models import MarketBar
from silverpilot.app.providers.errors import (
    DataQualityError,
    ProviderParseError,
    ProviderUnavailableError,
)
from silverpilot.app.providers.yahoo_finance import (
    YAHOO_RESEARCH_SOURCE_NAME,
    YahooFinanceReferenceProvider,
)


@dataclass(frozen=True)
class ReferenceBackfillResult:
    run: ReferenceDataBackfillRunModel
    bars_fetched: int
    rows_inserted: int
    rows_updated: int
    status: str


def backfill_reference_bars(
    session: Session,
    *,
    instrument: ReferenceMarketInstrumentModel | FxReferenceInstrumentModel,
    provider: ReferenceMarketDataProvider,
    timeframe: str,
    period: str,
    dry_run: bool,
    started_at: datetime | None = None,
) -> ReferenceBackfillResult:
    now = started_at or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("started_at must be timezone-aware")

    run = ReferenceDataBackfillRunModel(
        id=uuid4(),
        source=instrument.source,
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        timeframe=timeframe,
        period=period,
        rows_inserted=0,
        rows_updated=0,
        status="running",
        dry_run=dry_run,
        started_at=now,
        created_at=now,
    )
    session.add(run)
    session.flush()

    try:
        bars = list(
            provider.fetch_bars(
                symbol=instrument.symbol,
                timeframe=timeframe,
                period=period,
            )
        )
        if not bars:
            raise ValueError("reference provider returned no bars")
        data_hash = _bars_hash(bars)
        previous_hash = session.scalar(
            select(ReferenceDataBackfillRunModel.data_hash)
            .where(
                ReferenceDataBackfillRunModel.source == instrument.source,
                ReferenceDataBackfillRunModel.instrument_id == instrument.id,
                ReferenceDataBackfillRunModel.symbol == instrument.symbol,
                ReferenceDataBackfillRunModel.timeframe == timeframe,
                ReferenceDataBackfillRunModel.period == period,
                ReferenceDataBackfillRunModel.status.in_(("dry_run", "completed")),
                ReferenceDataBackfillRunModel.data_hash.is_not(None),
                ReferenceDataBackfillRunModel.id != run.id,
            )
            .order_by(ReferenceDataBackfillRunModel.started_at.desc())
            .limit(1)
        )
        actual_start_at = min(bar.bar_start_at for bar in bars)
        actual_end_at = max(bar.bar_end_at for bar in bars)

        inserted = 0
        updated = 0
        if not dry_run:
            inserted, updated = _persist_bars(
                session,
                bars=bars,
                instrument_id=instrument.id,
                source=instrument.source,
                timeframe=timeframe,
                backfill_batch_id=run.id,
                stored_at=now,
            )

        run.rows_inserted = inserted
        run.rows_updated = updated
        run.data_hash = data_hash
        run.feasibility_summary = _feasibility_summary(
            provider=provider,
            bars=bars,
            data_hash=data_hash,
            previous_hash=previous_hash,
            actual_start_at=actual_start_at,
            actual_end_at=actual_end_at,
            fetched_at=now,
        )
        run.actual_start_at = actual_start_at
        run.actual_end_at = actual_end_at
        run.status = "dry_run" if dry_run else "completed"
        run.finished_at = now
        session.flush()
        return ReferenceBackfillResult(
            run=run,
            bars_fetched=len(bars),
            rows_inserted=inserted,
            rows_updated=updated,
            status=run.status,
        )
    except (DataQualityError, ProviderParseError, ProviderUnavailableError, ValueError) as exc:
        run.status = "failed"
        run.error_summary = str(exc)[:1000]
        run.finished_at = now
        if run.source == YAHOO_RESEARCH_SOURCE_NAME:
            session.add(
                SystemHealthEventModel(
                    id=uuid4(),
                    component="yahoo_research_backfill",
                    status="degraded",
                    severity="warning",
                    message="Yahoo research backfill failed; no bars written",
                    payload={
                        "source": run.source,
                        "symbol": run.symbol,
                        "timeframe": run.timeframe,
                        "period": run.period,
                        "dry_run": run.dry_run,
                        "error": run.error_summary,
                    },
                    occurred_at=now,
                    created_at=now,
                )
            )
        session.flush()
        return ReferenceBackfillResult(
            run=run,
            bars_fetched=0,
            rows_inserted=0,
            rows_updated=0,
            status=run.status,
        )


def create_blocked_reference_backfill_run(
    session: Session,
    *,
    source: str,
    symbol: str,
    timeframe: str,
    period: str,
    reason: str,
    instrument_id: UUID | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> ReferenceDataBackfillRunModel | None:
    created_at = now or datetime.now(UTC)
    if instrument_id is None:
        return None
    run = ReferenceDataBackfillRunModel(
        id=uuid4(),
        source=source,
        instrument_id=instrument_id,
        symbol=symbol,
        timeframe=timeframe,
        period=period,
        rows_inserted=0,
        rows_updated=0,
        status="blocked",
        error_summary=reason,
        dry_run=dry_run,
        started_at=created_at,
        finished_at=created_at,
        created_at=created_at,
    )
    session.add(run)
    session.flush()
    return run


def _persist_bars(
    session: Session,
    *,
    bars: Sequence[MarketBar],
    instrument_id: UUID,
    source: str,
    timeframe: str,
    backfill_batch_id: UUID,
    stored_at: datetime,
) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for bar in sorted(bars, key=lambda item: item.bar_start_at):
        if bar.instrument_type != InstrumentType.REFERENCE:
            raise ValueError("reference backfill can persist only reference bars")
        if bar.instrument_id != instrument_id:
            raise ValueError("provider returned a bar for a different instrument")
        if bar.source != source:
            raise ValueError("provider returned a bar for a different source")
        if bar.timeframe != timeframe:
            raise ValueError("provider returned a bar for a different timeframe")

        existing = session.scalar(
            select(MarketBarModel).where(
                MarketBarModel.instrument_type == InstrumentType.REFERENCE.value,
                MarketBarModel.instrument_id == instrument_id,
                MarketBarModel.source == source,
                MarketBarModel.timeframe == timeframe,
                MarketBarModel.bar_start_at == bar.bar_start_at,
            )
        )
        values = _bar_values(bar, backfill_batch_id=backfill_batch_id, stored_at=stored_at)
        if existing is None:
            session.add(MarketBarModel(id=bar.id, created_at=stored_at, **values))
            inserted += 1
        else:
            for field_name, value in values.items():
                setattr(existing, field_name, value)
            existing.updated_at = stored_at
            updated += 1
    session.flush()
    return inserted, updated


def _bar_values(
    bar: MarketBar,
    *,
    backfill_batch_id: UUID,
    stored_at: datetime,
) -> dict[str, object]:
    effective_stored_at = stored_at
    if bar.fetched_at is not None and effective_stored_at < bar.fetched_at:
        effective_stored_at = bar.fetched_at
    return {
        "instrument_type": bar.instrument_type.value,
        "instrument_id": bar.instrument_id,
        "source": bar.source,
        "timeframe": bar.timeframe,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "quote_count": bar.quote_count,
        "bar_start_at": bar.bar_start_at,
        "bar_end_at": bar.bar_end_at,
        "provider_reported_at": bar.provider_reported_at,
        "fetched_at": bar.fetched_at,
        "stored_at": effective_stored_at,
        "data_delay_seconds": bar.data_delay_seconds,
        "signal_available_at": bar.signal_available_at,
        "adjusted_close": bar.adjusted_close,
        "volume": bar.volume,
        "data_quality_status": bar.data_quality_status.value,
        "session_status": bar.session_status.value,
        "is_backfilled": True,
        "backfill_batch_id": backfill_batch_id,
    }


def _bars_hash(bars: Sequence[MarketBar]) -> str:
    payload = [
        {
            "source": bar.source,
            "timeframe": bar.timeframe,
            "bar_start_at": bar.bar_start_at.isoformat(),
            "bar_end_at": bar.bar_end_at.isoformat(),
            "open": _decimal_text(bar.open),
            "high": _decimal_text(bar.high),
            "low": _decimal_text(bar.low),
            "close": _decimal_text(bar.close),
            "adjusted_close": _decimal_text(bar.adjusted_close),
            "volume": _decimal_text(bar.volume),
        }
        for bar in sorted(bars, key=lambda item: (item.source, item.timeframe, item.bar_start_at))
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def _feasibility_summary(
    *,
    provider: ReferenceMarketDataProvider,
    bars: Sequence[MarketBar],
    data_hash: str,
    previous_hash: str | None,
    actual_start_at: datetime,
    actual_end_at: datetime,
    fetched_at: datetime,
) -> dict[str, object]:
    provider_summary: dict[str, object] = {}
    if (
        isinstance(provider, YahooFinanceReferenceProvider)
        and provider.last_parse_result is not None
    ):
        parsed = provider.last_parse_result
        provider_summary = {
            "provider_interval": parsed.provider_interval,
            "requested_timeframe": parsed.requested_timeframe,
            "normalized_timeframe": parsed.normalized_timeframe,
            "normalization": (
                "provider interval 1h aggregated to SilverPilot 4h"
                if parsed.provider_interval == "1h" and parsed.normalized_timeframe == "4h"
                else "native"
            ),
            "timezone": parsed.metadata.timezone,
            "exchange": parsed.metadata.exchange,
            "currency": parsed.metadata.currency,
            "source_payload_hash": parsed.source_hash,
            "raw_bar_count": parsed.raw_bar_count,
            "dropped_partial_groups": parsed.dropped_partial_groups,
        }

    sorted_bars = sorted(bars, key=lambda item: item.bar_start_at)
    cadence_gaps = _cadence_gaps(sorted_bars)
    final_bar_lag_minutes = int((fetched_at - sorted_bars[-1].bar_end_at).total_seconds() // 60)
    summary = {
        **provider_summary,
        "bar_count": len(sorted_bars),
        "actual_start_at": actual_start_at.isoformat(),
        "actual_end_at": actual_end_at.isoformat(),
        "weekend_bar_count": sum(1 for bar in sorted_bars if bar.bar_start_at.weekday() >= 5),
        "cadence_gap_count": len(cadence_gaps),
        "cadence_gaps": cadence_gaps[:20],
        "final_bar_lag_minutes": final_bar_lag_minutes,
        "data_hash": data_hash,
        "previous_data_hash": previous_hash,
        "repeat_hash_matches_previous": previous_hash == data_hash if previous_hash else None,
    }
    return summary


def _cadence_gaps(bars: Sequence[MarketBar]) -> list[dict[str, object]]:
    gaps: list[dict[str, object]] = []
    for previous, current in zip(bars, bars[1:], strict=False):
        expected = previous.bar_end_at
        if current.bar_start_at != expected:
            gaps.append(
                {
                    "previous_end_at": previous.bar_end_at.isoformat(),
                    "next_start_at": current.bar_start_at.isoformat(),
                    "gap_minutes": int(
                        (current.bar_start_at - previous.bar_end_at).total_seconds() // 60
                    ),
                }
            )
    return gaps


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")
