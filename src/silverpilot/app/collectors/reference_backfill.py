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
    MarketBarModel,
    ReferenceDataBackfillRunModel,
    ReferenceMarketInstrumentModel,
)
from silverpilot.app.domain.enums import InstrumentType
from silverpilot.app.domain.interfaces import ReferenceMarketDataProvider
from silverpilot.app.domain.models import MarketBar
from silverpilot.app.providers.errors import (
    DataQualityError,
    ProviderParseError,
    ProviderUnavailableError,
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
    instrument: ReferenceMarketInstrumentModel,
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


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")
