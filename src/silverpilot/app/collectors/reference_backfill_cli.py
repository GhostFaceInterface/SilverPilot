import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from silverpilot.app.collectors.reference_backfill import (
    backfill_reference_bars,
    create_blocked_reference_backfill_run,
)
from silverpilot.app.core.settings import Settings
from silverpilot.app.db.models import ReferenceDataBackfillRunModel, ReferenceMarketInstrumentModel
from silverpilot.app.db.session import create_db_engine
from silverpilot.app.providers.yahoo_finance import (
    YAHOO_RESEARCH_SOURCE_NAME,
    YahooFinanceReferenceProvider,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill approved delayed reference market bars.")
    parser.add_argument("--source", required=True, help="Approved reference source code.")
    parser.add_argument("--symbol", required=True, help="Reference symbol to backfill.")
    parser.add_argument("--timeframe", default="4h", help="Reference bar timeframe.")
    parser.add_argument("--period", default="2y", help="Provider-specific history period.")
    parser.add_argument("--instrument-id", type=UUID, default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--data-delay-seconds", type=int, default=None)
    parser.add_argument("--ingestion-delay-seconds", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.data_delay_seconds is not None and args.data_delay_seconds < 0:
        parser.error("--data-delay-seconds cannot be negative")
    if args.ingestion_delay_seconds is not None and args.ingestion_delay_seconds < 0:
        parser.error("--ingestion-delay-seconds cannot be negative")

    engine = create_db_engine(args.database_url)
    settings = Settings()
    now = datetime.now(UTC)
    with Session(engine) as session:
        instrument = _load_instrument(
            session,
            instrument_id=args.instrument_id,
            source=args.source,
            symbol=args.symbol,
        )
        blocked_reason = _blocked_reason(
            source=args.source,
            timeframe=args.timeframe,
            instrument=instrument,
            data_delay_seconds=args.data_delay_seconds,
        )
        if blocked_reason is not None:
            run = create_blocked_reference_backfill_run(
                session,
                source=args.source,
                symbol=args.symbol,
                timeframe=args.timeframe,
                period=args.period,
                reason=blocked_reason,
                instrument_id=instrument.id if instrument is not None else args.instrument_id,
                dry_run=args.dry_run,
                now=now,
            )
            session.commit()
            output = _blocked_output(
                reason=blocked_reason,
                source=args.source,
                symbol=args.symbol,
                timeframe=args.timeframe,
                period=args.period,
                dry_run=args.dry_run,
                run=run,
            )
            print(json.dumps(output, sort_keys=True))
            return 2

        assert instrument is not None
        data_delay_seconds = _effective_delay_seconds(
            instrument=instrument,
            override=args.data_delay_seconds,
        )
        assert data_delay_seconds is not None
        ingestion_delay_seconds = (
            args.ingestion_delay_seconds
            if args.ingestion_delay_seconds is not None
            else settings.reference_ingestion_delay_seconds
        )
        provider = YahooFinanceReferenceProvider(
            instrument_id=instrument.id,
            source=args.source,
            data_delay_seconds=data_delay_seconds,
            ingestion_delay_seconds=ingestion_delay_seconds,
        )
        result = backfill_reference_bars(
            session,
            instrument=instrument,
            provider=provider,
            timeframe=args.timeframe,
            period=args.period,
            dry_run=args.dry_run,
            started_at=now,
        )
        session.commit()
        output = {
            "status": result.status,
            "source": args.source,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "period": args.period,
            "dry_run": args.dry_run,
            "bars_fetched": result.bars_fetched,
            "rows_inserted": result.rows_inserted,
            "rows_updated": result.rows_updated,
            "data_hash": result.run.data_hash,
            "backfill_run_id": str(result.run.id),
        }
    print(json.dumps(output, sort_keys=True))
    return 0


def _load_instrument(
    session: Session,
    *,
    instrument_id: UUID | None,
    source: str,
    symbol: str,
) -> ReferenceMarketInstrumentModel | None:
    if instrument_id is not None:
        return session.get(ReferenceMarketInstrumentModel, instrument_id)
    return (
        session.query(ReferenceMarketInstrumentModel)
        .filter(
            ReferenceMarketInstrumentModel.source == source,
            ReferenceMarketInstrumentModel.symbol == symbol,
        )
        .one_or_none()
    )


def _blocked_reason(
    *,
    source: str,
    timeframe: str,
    instrument: ReferenceMarketInstrumentModel | None,
    data_delay_seconds: int | None,
) -> str | None:
    if source != YAHOO_RESEARCH_SOURCE_NAME:
        return (
            "reference ingestion is blocked until docs/source-feasibility-v1.md "
            "approves a runtime source, FX source, terms status, timestamp policy, "
            "session calendar, timeframe, and historical depth"
        )
    if timeframe not in {"1h", "4h", "1d"}:
        return "yahoo_research backfill supports only 1h, 4h, and 1d timeframes"
    if instrument is None:
        return "reference_market_instruments row is required before yahoo_research backfill"
    if instrument.source_terms_status != "research_only":
        return "yahoo_research requires source_terms_status=research_only"
    if _effective_delay_seconds(instrument=instrument, override=data_delay_seconds) is None:
        return "yahoo_research requires data_delay_seconds on the instrument or CLI override"
    return None


def _effective_delay_seconds(
    *,
    instrument: ReferenceMarketInstrumentModel,
    override: int | None,
) -> int | None:
    if override is not None:
        if override < 0:
            raise ValueError("--data-delay-seconds cannot be negative")
        return override
    return instrument.data_delay_seconds


def _blocked_output(
    *,
    reason: str,
    source: str,
    symbol: str,
    timeframe: str,
    period: str,
    dry_run: bool,
    run: ReferenceDataBackfillRunModel | None,
) -> dict[str, object]:
    return {
        "status": "blocked",
        "reason": reason,
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "period": period,
        "dry_run": dry_run,
        "backfill_run_id": str(run.id) if run is not None else None,
    }


if __name__ == "__main__":
    raise SystemExit(main())
