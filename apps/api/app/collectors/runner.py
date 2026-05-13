import argparse
import os
import time
from datetime import UTC, datetime
from decimal import Decimal

from app.collectors.public_sources import (
    collect_fed_rss,
    collect_fred_macro,
    collect_kuveyt_public_silver,
    collect_stooq_xag_usd,
    collect_tcmb_usd_try,
)
from app.collectors.service import ingest_manual_price
from app.core.db import SessionLocal
from app.schemas.collectors import ManualPriceIngestRequest


def run_once(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        if args.job == "kuveyt-silver":
            run, raw_inserted, snapshot = collect_kuveyt_public_silver(db)
            snapshot_id = snapshot.id if snapshot is not None else None
            print(
                f"collector_run_id={run.id} status={run.status} "
                f"raw_inserted={raw_inserted} snapshot_id={snapshot_id}",
                flush=True,
            )
            return
        if args.job == "stooq-xag-usd":
            run, raw_inserted, snapshot = collect_stooq_xag_usd(db)
            snapshot_id = snapshot.id if snapshot is not None else None
            print(
                f"collector_run_id={run.id} status={run.status} "
                f"raw_inserted={raw_inserted} snapshot_id={snapshot_id}",
                flush=True,
            )
            return
        if args.job == "tcmb-usd-try":
            run, raw_inserted = collect_tcmb_usd_try(db)
            print(f"collector_run_id={run.id} status={run.status} raw_inserted={raw_inserted}", flush=True)
            return
        if args.job == "fed-rss":
            run, inserted = collect_fed_rss(db)
            print(f"collector_run_id={run.id} status={run.status} records_inserted={inserted}", flush=True)
            return
        if args.job == "fred-macro":
            run, inserted = collect_fred_macro(db)
            print(f"collector_run_id={run.id} status={run.status} records_inserted={inserted}", flush=True)
            return

        request = ManualPriceIngestRequest(
            source_type=args.source_type,
            source=args.source,
            asset_symbol=args.asset_symbol,
            buy_price=args.buy_price,
            sell_price=args.sell_price,
            currency=args.currency,
            observed_at=datetime.now(UTC),
            payload={"runner": "manual_scheduled"},
        )
        run, raw_inserted, snapshot = ingest_manual_price(db, request)
        snapshot_id = snapshot.id if snapshot is not None else None
        print(
            f"collector_run_id={run.id} status={run.status} "
            f"raw_inserted={raw_inserted} snapshot_id={snapshot_id}",
            flush=True,
        )
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SilverPilot collector jobs.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("COLLECTOR_INTERVAL_SECONDS", "900")))
    parser.add_argument(
        "--job",
        choices=["manual", "kuveyt-silver", "stooq-xag-usd", "tcmb-usd-try", "fed-rss", "fred-macro"],
        default=os.getenv("COLLECTOR_JOB", "manual"),
    )
    parser.add_argument("--source-type", choices=["bank", "global"], default=os.getenv("MANUAL_PRICE_SOURCE_TYPE", "bank"))
    parser.add_argument("--source", default=os.getenv("MANUAL_PRICE_SOURCE", "manual-scheduled"))
    parser.add_argument("--asset-symbol", default=os.getenv("MANUAL_PRICE_ASSET_SYMBOL", "XAG"))
    parser.add_argument("--buy-price", type=Decimal, default=Decimal(os.getenv("MANUAL_PRICE_BUY_PRICE", "10.00")))
    parser.add_argument("--sell-price", type=Decimal, default=Decimal(os.getenv("MANUAL_PRICE_SELL_PRICE", "9.80")))
    parser.add_argument("--currency", default=os.getenv("MANUAL_PRICE_CURRENCY", "USD"))
    args = parser.parse_args()

    if args.interval_seconds <= 0:
        raise ValueError("interval-seconds must be greater than zero")

    run_once(args)
    while args.loop:
        time.sleep(args.interval_seconds)
        run_once(args)


if __name__ == "__main__":
    main()
