import argparse
import logging
import os
import time
from datetime import UTC, datetime
from decimal import Decimal

from app.collectors.public_sources import (
    collect_fed_rss,
    collect_fred_macro,
    collect_global_xag_usd,
    collect_kuveyt_public_silver,
    collect_kuveyt_usd_try,
    collect_yahoo_usd_try,
    collect_tcmb_usd_try,
)
from app.collectors.service import ingest_manual_price
from app.core.db import SessionLocal
from app.schemas.collectors import ManualPriceIngestRequest

JOB_CHOICES = (
    "manual",
    "kuveyt-silver",
    "global-xag-usd",
    "yahoo-usd-try",
    "kuveyt-usd-try",
    "tcmb-usd-try",
    "fed-rss",
    "fred-macro",
)


def run_once(args: argparse.Namespace, job: str | None = None) -> bool:
    selected_job = job or args.job
    db = SessionLocal()
    try:
        if selected_job == "kuveyt-silver":
            run, raw_inserted, snapshot = collect_kuveyt_public_silver(db)
            snapshot_id = snapshot.id if snapshot is not None else None
            print(
                f"job={selected_job} collector_run_id={run.id} status={run.status} "
                f"raw_inserted={raw_inserted} snapshot_id={snapshot_id}",
                flush=True,
            )
            return run.status == "success"
        if selected_job == "yahoo-usd-try":
            run, raw_inserted = collect_yahoo_usd_try(db)
            print(
                f"job={selected_job} collector_run_id={run.id} status={run.status} raw_inserted={raw_inserted}",
                flush=True,
            )
            return run.status == "success"

        if selected_job == "kuveyt-usd-try":
            from app.core.config import get_settings

            run, raw_inserted = collect_kuveyt_usd_try(db, settings=get_settings())
            print(
                f"job={selected_job} collector_run_id={run.id} status={run.status} raw_inserted={raw_inserted}",
                flush=True,
            )
            return run.status == "success"
        if selected_job == "global-xag-usd":
            run, raw_inserted, snapshot = collect_global_xag_usd(db)
            snapshot_id = snapshot.id if snapshot is not None else None
            print(
                f"job={selected_job} collector_run_id={run.id} status={run.status} "
                f"raw_inserted={raw_inserted} snapshot_id={snapshot_id}",
                flush=True,
            )
            if not raw_inserted or snapshot_id is None:
                logging.getLogger("app.collectors.runner").error(
                    f"Data insertion failed for job={selected_job}: raw_inserted={raw_inserted}, snapshot_id={snapshot_id}. "
                    f"status={run.status}, error_message={run.error_message}, details={run.details_json}"
                )
            from app.core.config import get_settings

            settings = get_settings()
            if settings.auto_trading_enabled:
                import asyncio
                from app.services.auto_trader import run_auto_trading

                try:
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                    if loop and loop.is_running():
                        asyncio.ensure_future(run_auto_trading())
                    else:
                        asyncio.run(run_auto_trading())
                except Exception as e:
                    print(f"Error running auto trading: {e}", flush=True)
            return run.status == "success"
        if selected_job == "tcmb-usd-try":
            run, raw_inserted = collect_tcmb_usd_try(db)
            print(
                f"job={selected_job} collector_run_id={run.id} status={run.status} raw_inserted={raw_inserted}",
                flush=True,
            )
            return run.status == "success"
        if selected_job == "fed-rss":
            run, inserted = collect_fed_rss(db)
            print(
                f"job={selected_job} collector_run_id={run.id} status={run.status} records_inserted={inserted}",
                flush=True,
            )
            return run.status == "success"
        if selected_job == "fred-macro":
            run, inserted = collect_fred_macro(db)
            print(
                f"job={selected_job} collector_run_id={run.id} status={run.status} records_inserted={inserted}",
                flush=True,
            )
            return run.status == "success"

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
            f"job={selected_job} collector_run_id={run.id} status={run.status} "
            f"raw_inserted={raw_inserted} snapshot_id={snapshot_id}",
            flush=True,
        )
        return run.status == "success"
    finally:
        db.close()


def run_jobs(args: argparse.Namespace) -> bool:
    success = True
    for job in parse_collector_jobs(args.jobs, fallback_job=args.job):
        success = run_once(args, job=job) and success
    return success


def parse_collector_jobs(value: str, *, fallback_job: str) -> list[str]:
    jobs = [item.strip() for item in value.split(",") if item.strip()]
    if not jobs:
        return [fallback_job]
    unknown = [job for job in jobs if job not in JOB_CHOICES]
    if unknown:
        raise ValueError(f"Unsupported collector job(s): {', '.join(unknown)}")
    return jobs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Run SilverPilot collector jobs.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("COLLECTOR_INTERVAL_SECONDS", "900")))
    parser.add_argument(
        "--jobs",
        default=os.getenv("COLLECTOR_JOBS", ""),
        help="Comma-separated collector jobs. When set, this overrides --job.",
    )
    parser.add_argument(
        "--job",
        choices=JOB_CHOICES,
        default=os.getenv("COLLECTOR_JOB", "manual"),
    )
    parser.add_argument(
        "--source-type", choices=["bank", "global"], default=os.getenv("MANUAL_PRICE_SOURCE_TYPE", "bank")
    )
    parser.add_argument("--source", default=os.getenv("MANUAL_PRICE_SOURCE", "manual-scheduled"))
    parser.add_argument("--asset-symbol", default=os.getenv("MANUAL_PRICE_ASSET_SYMBOL", "XAG"))
    parser.add_argument("--buy-price", type=Decimal, default=Decimal(os.getenv("MANUAL_PRICE_BUY_PRICE", "10.00")))
    parser.add_argument("--sell-price", type=Decimal, default=Decimal(os.getenv("MANUAL_PRICE_SELL_PRICE", "9.80")))
    parser.add_argument("--currency", default=os.getenv("MANUAL_PRICE_CURRENCY", "USD"))
    args = parser.parse_args()

    if args.interval_seconds <= 0:
        raise ValueError("interval-seconds must be greater than zero")

    success = run_jobs(args)
    if not args.loop and not success:
        raise SystemExit(1)
    while args.loop:
        time.sleep(args.interval_seconds)
        run_jobs(args)


if __name__ == "__main__":
    main()
