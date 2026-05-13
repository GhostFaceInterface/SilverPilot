import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, CollectorRun, PriceSnapshot, RawBankPrice, RawFxRate, RawGlobalPrice, RawNews
from app.schemas.collectors import ManualPriceIngestRequest

PRICE_QUANT = Decimal("0.000001")


class CollectorError(ValueError):
    pass


def payload_hash(payload: bytes | str | dict) -> str:
    if isinstance(payload, bytes):
        raw = payload
    elif isinstance(payload, str):
        raw = payload.encode("utf-8")
    else:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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
        fetched_at=datetime.now(UTC),
        raw_payload_hash=payload_hash(request.payload),
        parser_version="manual-v1",
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


def ingest_global_price(
    db: Session,
    *,
    source: str,
    asset_symbol: str,
    buy_price: Decimal,
    sell_price: Decimal,
    currency: str,
    observed_at: datetime,
    fetched_at: datetime,
    payload: dict,
    raw_payload: str,
    parser_version: str,
    collector_name: str,
) -> tuple[CollectorRun, bool, PriceSnapshot | None]:
    asset = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()
    if asset is None:
        raise CollectorError(f"Asset not found: {asset_symbol}")

    observed_at = _utc(observed_at)
    fetched_at = _utc(fetched_at)
    run = start_collector_run(
        db,
        collector_name=collector_name,
        source=source,
        records_seen=1,
        details_json={"asset_symbol": asset_symbol, "currency": currency.upper()},
    )
    duplicate = db.execute(
        select(RawGlobalPrice).where(
            RawGlobalPrice.asset_id == asset.id,
            RawGlobalPrice.source == source,
            RawGlobalPrice.observed_at == observed_at,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        finish_collector_run(db, run, status="success", duplicates=1)
        db.commit()
        db.refresh(run)
        return run, False, None

    raw_hash = payload_hash(raw_payload)
    raw = RawGlobalPrice(
        collector_run_id=run.id,
        asset_id=asset.id,
        source=source,
        buy_price=_price(buy_price),
        sell_price=_price(sell_price),
        currency=currency.upper(),
        observed_at=observed_at,
        fetched_at=fetched_at,
        raw_payload_hash=raw_hash,
        parser_version=parser_version,
        payload_json=payload,
    )
    db.add(raw)

    spread_absolute = _price(buy_price - sell_price)
    mid_price = _price((buy_price + sell_price) / Decimal("2"))
    spread_percent = _price((spread_absolute / mid_price) * Decimal("100")) if mid_price > 0 else Decimal("0.000000")
    snapshot = PriceSnapshot(
        asset_id=asset.id,
        source=source,
        buy_price=_price(buy_price),
        sell_price=_price(sell_price),
        mid_price=mid_price,
        currency=currency.upper(),
        spread_absolute=spread_absolute,
        spread_percent=spread_percent,
        observed_at=observed_at,
    )
    db.add(snapshot)

    finish_collector_run(db, run, status="success", records_inserted=1)
    db.commit()
    db.refresh(run)
    db.refresh(snapshot)
    return run, True, snapshot


def ingest_bank_price(
    db: Session,
    *,
    source: str,
    asset_symbol: str,
    buy_price: Decimal,
    sell_price: Decimal,
    currency: str,
    observed_at: datetime,
    fetched_at: datetime,
    payload: dict,
    raw_payload: str,
    parser_version: str,
    collector_name: str,
) -> tuple[CollectorRun, bool, PriceSnapshot | None]:
    asset = db.execute(select(Asset).where(Asset.symbol == asset_symbol)).scalar_one_or_none()
    if asset is None:
        raise CollectorError(f"Asset not found: {asset_symbol}")

    observed_at = _utc(observed_at)
    fetched_at = _utc(fetched_at)
    run = start_collector_run(
        db,
        collector_name=collector_name,
        source=source,
        records_seen=1,
        details_json={"asset_symbol": asset_symbol, "currency": currency.upper()},
    )
    duplicate = db.execute(
        select(RawBankPrice).where(
            RawBankPrice.asset_id == asset.id,
            RawBankPrice.source == source,
            RawBankPrice.observed_at == observed_at,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        finish_collector_run(db, run, status="success", duplicates=1)
        db.commit()
        db.refresh(run)
        return run, False, None

    db.add(
        RawBankPrice(
            collector_run_id=run.id,
            asset_id=asset.id,
            source=source,
            buy_price=_price(buy_price),
            sell_price=_price(sell_price),
            currency=currency.upper(),
            observed_at=observed_at,
            fetched_at=fetched_at,
            raw_payload_hash=payload_hash(raw_payload),
            parser_version=parser_version,
            payload_json=payload,
        )
    )

    spread_absolute = _price(buy_price - sell_price)
    mid_price = _price((buy_price + sell_price) / Decimal("2"))
    spread_percent = _price((spread_absolute / mid_price) * Decimal("100")) if mid_price > 0 else Decimal("0.000000")
    snapshot = PriceSnapshot(
        asset_id=asset.id,
        source=source,
        buy_price=_price(buy_price),
        sell_price=_price(sell_price),
        mid_price=mid_price,
        currency=currency.upper(),
        spread_absolute=spread_absolute,
        spread_percent=spread_percent,
        observed_at=observed_at,
    )
    db.add(snapshot)

    finish_collector_run(db, run, status="success", records_inserted=1)
    db.commit()
    db.refresh(run)
    db.refresh(snapshot)
    return run, True, snapshot


def ingest_fx_rate(
    db: Session,
    *,
    source: str,
    base_currency: str,
    quote_currency: str,
    rate: Decimal,
    observed_at: datetime,
    fetched_at: datetime,
    payload: dict,
    raw_payload: str,
    parser_version: str,
    collector_name: str,
) -> tuple[CollectorRun, bool]:
    observed_at = _utc(observed_at)
    fetched_at = _utc(fetched_at)
    source = source.lower()
    base_currency = base_currency.upper()
    quote_currency = quote_currency.upper()
    run = start_collector_run(
        db,
        collector_name=collector_name,
        source=source,
        records_seen=1,
        details_json={"base_currency": base_currency, "quote_currency": quote_currency},
    )
    duplicate = db.execute(
        select(RawFxRate).where(
            RawFxRate.source == source,
            RawFxRate.base_currency == base_currency,
            RawFxRate.quote_currency == quote_currency,
            RawFxRate.observed_at == observed_at,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        finish_collector_run(db, run, status="success", duplicates=1)
        db.commit()
        db.refresh(run)
        return run, False

    db.add(
        RawFxRate(
            collector_run_id=run.id,
            source=source,
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate=_price(rate),
            observed_at=observed_at,
            fetched_at=fetched_at,
            raw_payload_hash=payload_hash(raw_payload),
            parser_version=parser_version,
            payload_json=payload,
        )
    )
    finish_collector_run(db, run, status="success", records_inserted=1)
    db.commit()
    db.refresh(run)
    return run, True


def ingest_news_items(
    db: Session,
    *,
    collector_name: str,
    source: str,
    items: list[dict],
    fetched_at: datetime,
    raw_payload: str,
    parser_version: str,
) -> tuple[CollectorRun, int]:
    fetched_at = _utc(fetched_at)
    source = source.lower()
    run = start_collector_run(
        db,
        collector_name=collector_name,
        source=source,
        records_seen=len(items),
        details_json={"parser_version": parser_version, "raw_payload_hash": payload_hash(raw_payload)},
    )
    inserted = 0
    duplicates = 0
    for item in items:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            raise CollectorError("News item title and URL are required")
        duplicate = db.execute(select(RawNews).where(RawNews.source == source, RawNews.url == url)).scalar_one_or_none()
        if duplicate is not None:
            duplicates += 1
            continue

        payload = dict(item)
        published_at = payload.get("published_at")
        if published_at is not None:
            published_at = _utc(published_at)
            payload["published_at"] = published_at.isoformat()
        db.add(
            RawNews(
                collector_run_id=run.id,
                source=source,
                title=title,
                url=url,
                published_at=published_at,
                fetched_at=fetched_at,
                raw_payload_hash=payload_hash(payload),
                parser_version=parser_version,
                payload_json=payload,
            )
        )
        inserted += 1

    finish_collector_run(db, run, status="success", records_inserted=inserted, duplicates=duplicates)
    db.commit()
    db.refresh(run)
    return run, inserted


def start_collector_run(
    db: Session,
    *,
    collector_name: str,
    source: str,
    records_seen: int = 0,
    details_json: dict | None = None,
) -> CollectorRun:
    run = CollectorRun(
        collector_name=collector_name,
        source=source,
        status="running",
        records_seen=records_seen,
        records_inserted=0,
        duplicates=0,
        details_json=details_json or {},
    )
    db.add(run)
    db.flush()
    return run


def finish_collector_run(
    db: Session,
    run: CollectorRun,
    *,
    status: str,
    records_inserted: int = 0,
    duplicates: int = 0,
    error_message: str | None = None,
) -> CollectorRun:
    run.status = status
    run.records_inserted = records_inserted
    run.duplicates = duplicates
    run.error_message = error_message
    run.finished_at = datetime.now(UTC)
    db.flush()
    return run


def record_failed_run(
    db: Session,
    *,
    collector_name: str,
    source: str,
    error_message: str,
    details_json: dict | None = None,
) -> CollectorRun:
    run = start_collector_run(db, collector_name=collector_name, source=source, details_json=details_json)
    finish_collector_run(db, run, status="failed", error_message=error_message)
    db.commit()
    db.refresh(run)
    return run


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
