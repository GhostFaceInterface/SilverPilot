import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from silverpilot.app.db.models import ReferenceDataBackfillRunModel, ReferenceMarketInstrumentModel
from silverpilot.app.db.session import create_db_engine


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill approved delayed reference market bars."
    )
    parser.add_argument("--source", required=True, help="Approved reference source code.")
    parser.add_argument("--symbol", required=True, help="Reference symbol to backfill.")
    parser.add_argument("--timeframe", default="4h", help="Reference bar timeframe.")
    parser.add_argument("--period", default="2y", help="Provider-specific history period.")
    parser.add_argument("--instrument-id", type=UUID, default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    engine = create_db_engine(args.database_url)
    now = datetime.now(UTC)
    with Session(engine) as session:
        instrument = _load_instrument(
            session,
            instrument_id=args.instrument_id,
            source=args.source,
            symbol=args.symbol,
        )
        status = "blocked"
        reason = (
            "reference ingestion is blocked until docs/source-feasibility-v1.md "
            "approves a runtime source, FX source, terms status, timestamp policy, "
            "session calendar, timeframe, and historical depth"
        )
        run = ReferenceDataBackfillRunModel(
            id=uuid4(),
            source=args.source,
            instrument_id=instrument.id if instrument is not None else args.instrument_id,
            symbol=args.symbol,
            timeframe=args.timeframe,
            period=args.period,
            rows_inserted=0,
            rows_updated=0,
            status=status,
            error_summary=reason,
            dry_run=args.dry_run,
            started_at=now,
            finished_at=now,
            created_at=now,
        )
        if run.instrument_id is not None:
            session.add(run)
            session.commit()

        output = {
            "status": status,
            "reason": reason,
            "source": args.source,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "period": args.period,
            "dry_run": args.dry_run,
            "backfill_run_id": str(run.id) if run.instrument_id is not None else None,
        }
    print(json.dumps(output, sort_keys=True))
    return 2


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


if __name__ == "__main__":
    raise SystemExit(main())
