from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, CollectorRun, PriceSnapshot, RawBankPrice, RawGlobalPrice
from app.schemas.collectors import ManualPriceIngestRequest

PRICE_QUANT = Decimal("0.000001")


class CollectorError(ValueError):
    pass


def ingest_manual_price(db: Session, request: ManualPriceIngestRequest) -> tuple[CollectorRun, bool, PriceSnapshot | None]:
    asset = db.execute(select(Asset).where(Asset.symbol == request.asset_symbol)).scalar_one_or_none()
    if asset is None:
        raise CollectorError(f"Asset not found: {request.asset_symbol}")

    observed_at = _utc(request.observed_at)
    collector_name = f"manual_{request.source_type}_price"
    run = CollectorRun(
        collector_name=collector_name,
        source=request.source,
        status="running",
        records_seen=1,
        records_inserted=0,
        duplicates=0,
        details_json={"asset_symbol": request.asset_symbol, "source_type": request.source_type},
    )
    db.add(run)
    db.flush()

    raw_model = RawBankPrice if request.source_type == "bank" else RawGlobalPrice
    duplicate = db.execute(
        select(raw_model).where(
            raw_model.asset_id == asset.id,
            raw_model.source == request.source,
            raw_model.observed_at == observed_at,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        run.status = "success"
        run.duplicates = 1
        run.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(run)
        return run, False, None

    raw = raw_model(
        collector_run_id=run.id,
        asset_id=asset.id,
        source=request.source,
        buy_price=_price(request.buy_price),
        sell_price=_price(request.sell_price),
        currency=request.currency.upper(),
        observed_at=observed_at,
        payload_json=request.payload,
    )
    db.add(raw)

    spread_absolute = _price(request.buy_price - request.sell_price)
    mid_price = _price((request.buy_price + request.sell_price) / Decimal("2"))
    spread_percent = _price((spread_absolute / mid_price) * Decimal("100")) if mid_price > 0 else Decimal("0.000000")
    snapshot = PriceSnapshot(
        asset_id=asset.id,
        source=request.source,
        buy_price=_price(request.buy_price),
        sell_price=_price(request.sell_price),
        mid_price=mid_price,
        currency=request.currency.upper(),
        spread_absolute=spread_absolute,
        spread_percent=spread_percent,
        observed_at=observed_at,
    )
    db.add(snapshot)

    run.status = "success"
    run.records_inserted = 1
    run.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(run)
    db.refresh(snapshot)
    return run, True, snapshot


def latest_collector_run(db: Session) -> CollectorRun | None:
    return db.execute(select(CollectorRun).order_by(CollectorRun.started_at.desc()).limit(1)).scalar_one_or_none()


def collector_health(db: Session, stale_after_minutes: int = 60) -> dict:
    runs = db.execute(select(CollectorRun).order_by(CollectorRun.started_at.desc())).scalars()
    latest_by_collector: dict[tuple[str, str], CollectorRun] = {}
    for run in runs:
        key = (run.collector_name, run.source)
        if key not in latest_by_collector:
            latest_by_collector[key] = run

    stale_after_seconds = stale_after_minutes * 60
    now = datetime.now(UTC)
    collectors = []
    for run in latest_by_collector.values():
        reference_time = _aware(run.finished_at or run.started_at)
        age_seconds = int((now - reference_time).total_seconds()) if reference_time is not None else None
        stale = age_seconds is None or age_seconds > stale_after_seconds
        collectors.append(
            {
                "collector_name": run.collector_name,
                "source": run.source,
                "status": run.status,
                "records_seen": run.records_seen,
                "records_inserted": run.records_inserted,
                "duplicates": run.duplicates,
                "age_seconds": age_seconds,
                "stale": stale,
                "error_message": run.error_message,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }
        )

    if not collectors:
        status = "empty"
    elif any(item["stale"] or item["status"] == "failed" for item in collectors):
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "stale_after_minutes": stale_after_minutes,
        "collectors": collectors,
    }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _price(value: Decimal) -> Decimal:
    return value.quantize(PRICE_QUANT)
