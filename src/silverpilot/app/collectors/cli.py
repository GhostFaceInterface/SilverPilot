import argparse
import json
from collections.abc import Sequence
from time import sleep
from uuid import UUID

from sqlalchemy.orm import Session

from silverpilot.app.collectors.price_collector import collect_bank_instrument_once
from silverpilot.app.db.session import create_db_engine
from silverpilot.app.providers.kuveyt_turk import KuveytTurkPriceProvider


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect Kuveyt Turk quotes.")
    parser.add_argument(
        "--bank-instrument-id",
        required=True,
        type=UUID,
        help="Active bank_instruments.id to collect for.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override SILVERPILOT_DATABASE_URL for this run.",
    )
    parser.add_argument(
        "--repeat",
        default=1,
        type=int,
        help="Number of bounded collection attempts to run.",
    )
    parser.add_argument(
        "--interval-seconds",
        default=60.0,
        type=float,
        help="Seconds to sleep between repeated collection attempts.",
    )
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be greater than or equal to 1")
    if args.interval_seconds < 0:
        parser.error("--interval-seconds must be greater than or equal to 0")

    engine = create_db_engine(args.database_url)
    provider = KuveytTurkPriceProvider()
    for attempt in range(1, args.repeat + 1):
        with Session(engine) as session:
            result = collect_bank_instrument_once(
                session,
                bank_instrument_id=args.bank_instrument_id,
                provider=provider,
                commit=True,
            )
            output = {
                "attempt": attempt,
                "quote_id": str(result.quote.id),
                "bank_instrument_id": str(result.quote.bank_instrument_id),
                "inserted": result.inserted,
                "committed": result.committed,
                "source": result.quote.source,
                "freshness_status": result.quote.freshness_status,
                "observed_at": result.quote.observed_at.isoformat(),
                "fetched_at": result.quote.fetched_at.isoformat(),
            }

        print(json.dumps(output, sort_keys=True))
        if attempt < args.repeat:
            sleep(args.interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
