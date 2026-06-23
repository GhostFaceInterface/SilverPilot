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
from silverpilot.app.db.models import (
    FxReferenceInstrumentModel,
    ReferenceDataBackfillRunModel,
    ReferenceMarketInstrumentModel,
)
from silverpilot.app.db.session import create_db_engine
from silverpilot.app.providers.yahoo_finance import (
    YAHOO_RESEARCH_SOURCE_NAME,
    YahooFinanceReferenceProvider,
)

CONSERVATIVE_YAHOO_DELAY_SECONDS = 1800
YAHOO_ACCEPTED_PAPER_RISK_STATUS = "owner_accepted_paper_use_risk"
YAHOO_LIVE_PAPER_SCOPE = "live-paper only"
YAHOO_APPROVED_TIMEFRAME = "1h"
YAHOO_APPROVED_SYMBOLS = {"SI=F", "TRY=X"}
YahooBackfillInstrument = ReferenceMarketInstrumentModel | FxReferenceInstrumentModel


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill approved delayed reference market bars.")
    parser.add_argument("--source", required=True, help="Approved reference source code.")
    parser.add_argument("--symbol", required=True, help="Reference symbol to backfill.")
    parser.add_argument(
        "--timeframe",
        default=YAHOO_APPROVED_TIMEFRAME,
        help="Reference bar timeframe.",
    )
    parser.add_argument("--period", default="2y", help="Provider-specific history period.")
    parser.add_argument("--instrument-id", type=UUID, default=None)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--data-delay-seconds", type=int, default=None)
    parser.add_argument("--ingestion-delay-seconds", type=int, default=None)
    parser.add_argument("--reviewed-dry-run-id", type=UUID, default=None)
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
        if blocked_reason is None:
            blocked_reason = _reviewed_dry_run_blocked_reason(
                session,
                instrument=instrument,
                source=args.source,
                symbol=args.symbol,
                timeframe=args.timeframe,
                period=args.period,
                dry_run=args.dry_run,
                reviewed_dry_run_id=args.reviewed_dry_run_id,
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
            "data_delay_seconds": data_delay_seconds,
            "source_delay_status": instrument.source_delay_status,
            "reviewed_dry_run_id": str(args.reviewed_dry_run_id)
            if args.reviewed_dry_run_id is not None
            else None,
            "bars_fetched": result.bars_fetched,
            "rows_inserted": result.rows_inserted,
            "rows_updated": result.rows_updated,
            "data_hash": result.run.data_hash,
            "feasibility_summary": result.run.feasibility_summary,
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
) -> YahooBackfillInstrument | None:
    if instrument_id is not None:
        reference = session.get(ReferenceMarketInstrumentModel, instrument_id)
        if reference is not None:
            return reference
        return session.get(FxReferenceInstrumentModel, instrument_id)
    reference = (
        session.query(ReferenceMarketInstrumentModel)
        .filter(
            ReferenceMarketInstrumentModel.source == source,
            ReferenceMarketInstrumentModel.symbol == symbol,
        )
        .one_or_none()
    )
    if reference is not None:
        return reference
    return (
        session.query(FxReferenceInstrumentModel)
        .filter(
            FxReferenceInstrumentModel.source == source,
            FxReferenceInstrumentModel.symbol == symbol,
        )
        .one_or_none()
    )


def _blocked_reason(
    *,
    source: str,
    timeframe: str,
    instrument: YahooBackfillInstrument | None,
    data_delay_seconds: int | None,
) -> str | None:
    if source != YAHOO_RESEARCH_SOURCE_NAME:
        return (
            "reference ingestion is blocked until docs/source-feasibility-v1.md "
            "approves a runtime source, FX source, terms status, timestamp policy, "
            "session calendar, timeframe, and historical depth"
        )
    if timeframe != YAHOO_APPROVED_TIMEFRAME:
        return "yahoo_research owner-accepted live-paper scope is limited to 1h"
    if instrument is None:
        return "reference_market_instruments row is required before yahoo_research backfill"
    if instrument.source_risk_status != YAHOO_ACCEPTED_PAPER_RISK_STATUS:
        return "yahoo_research requires source_risk_status=owner_accepted_paper_use_risk"
    if instrument.approved_scope != YAHOO_LIVE_PAPER_SCOPE:
        return "yahoo_research requires approved_scope=live-paper only"
    if instrument.approved_timeframe != YAHOO_APPROVED_TIMEFRAME:
        return "yahoo_research requires approved_timeframe=1h"
    if instrument.real_money_allowed:
        return "yahoo_research live-paper approval requires real_money_allowed=false"
    if instrument.symbol not in YAHOO_APPROVED_SYMBOLS:
        return "yahoo_research live-paper scope is limited to SI=F and TRY=X"
    if instrument.symbol not in _approved_symbols(instrument):
        return "yahoo_research symbol is outside the owner-approved symbol scope"
    if _effective_delay_seconds(instrument=instrument, override=data_delay_seconds) is None:
        return (
            "yahoo_research requires data_delay_seconds, CLI override, or "
            "source_delay_status=assumed_conservative"
        )
    return None


def _reviewed_dry_run_blocked_reason(
    session: Session,
    *,
    instrument: YahooBackfillInstrument | None,
    source: str,
    symbol: str,
    timeframe: str,
    period: str,
    dry_run: bool,
    reviewed_dry_run_id: UUID | None,
) -> str | None:
    if source != YAHOO_RESEARCH_SOURCE_NAME or dry_run:
        return None
    if instrument is None:
        return None
    if reviewed_dry_run_id is None:
        return "yahoo_research write backfill requires reviewed dry-run summary id"
    reviewed_run = session.get(ReferenceDataBackfillRunModel, reviewed_dry_run_id)
    if reviewed_run is None:
        return "reviewed dry-run summary id was not found"
    if reviewed_run.status != "dry_run" or not reviewed_run.dry_run:
        return "reviewed backfill run must be a dry-run summary"
    if reviewed_run.instrument_id != instrument.id:
        return "reviewed dry-run instrument does not match requested instrument"
    if (
        reviewed_run.source != source
        or reviewed_run.symbol != symbol
        or reviewed_run.timeframe != timeframe
        or reviewed_run.period != period
    ):
        return "reviewed dry-run source, symbol, timeframe, or period does not match"
    return None


def _effective_delay_seconds(
    *,
    instrument: YahooBackfillInstrument,
    override: int | None,
) -> int | None:
    if override is not None:
        if override < 0:
            raise ValueError("--data-delay-seconds cannot be negative")
        return override
    if instrument.data_delay_seconds is not None:
        return instrument.data_delay_seconds
    if instrument.source_delay_status == "assumed_conservative":
        return CONSERVATIVE_YAHOO_DELAY_SECONDS
    return None


def _approved_symbols(instrument: YahooBackfillInstrument) -> set[str]:
    if instrument.approved_symbols is None:
        return set()
    return {symbol.strip() for symbol in instrument.approved_symbols.split(",") if symbol.strip()}


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
