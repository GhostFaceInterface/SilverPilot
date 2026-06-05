import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Asset,
    CollectorRun,
    MarketBar,
    PriceSnapshot,
    RawBankPrice,
    RawEvent,
    RawFxRate,
    RawGlobalPrice,
    RawNews,
    TechnicalIndicator,
)
from app.schemas.collectors import ManualPriceIngestRequest
from app.services.indicators import calculate_indicators

logger = logging.getLogger(__name__)

PRICE_QUANT = Decimal("0.000001")
CONTEXT_COLLECTORS = {"fed_rss", "fred_macro"}
DEFAULT_COLLECTOR_JOBS = (
    "kuveyt-silver,global-xag-usd,tcmb-usd-try,fed-rss,fred-macro,"
    "hermes-agent,bloomberght-rss,fxstreet-rss,investing-rss"
)
GLOBAL_XAG_SOURCE_ALIASES = {
    "yahoo-si-f": "yahoo-si-f",
    "gold-api-xag-usd": "gold-api-xag-usd",
    "metals-dev": "metals-dev-silver-spot",
    "metals-dev-silver-spot": "metals-dev-silver-spot",
}
COLLECTOR_JOB_RUN_SOURCES = {
    "kuveyt-silver": {"kuveyt_public_silver": {"kuveyt-public-silver-page"}},
    "yahoo-usd-try": {"yahoo_usd_try": {"yahoo-usd-try"}},
    "kuveyt-usd-try": {"kuveyt_usd_try": {"kuveyt-public-silver-page"}},
    "tcmb-usd-try": {"tcmb_usd_try": {"tcmb-today-xml"}},
    "fed-rss": {"fed_rss": {"federal-reserve-rss"}},
    "fred-macro": {"fred_macro": {"fred-api"}},
    "bloomberght-rss": {"bloomberght_rss": {"bloomberght-rss"}},
    "fxstreet-rss": {"fxstreet_rss": {"fxstreet-rss"}},
    "investing-rss": {"investing_rss": {"investing-rss"}},
}


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


def ingest_manual_price(
    db: Session, request: ManualPriceIngestRequest
) -> tuple[CollectorRun, bool, PriceSnapshot | None]:
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
        collector_run_id=run.id,
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
        collector_run_id=run.id,
        asset_id=asset.id,
        source=source,
        buy_price=_price(buy_price),
        sell_price=_price(sell_price),
        mid_price=mid_price,
        currency=currency.upper(),
        spread_absolute=spread_absolute,
        spread_percent=spread_percent,
        observed_at=observed_at,
        resolved_source=source,
        is_degraded=False,
    )
    db.add(snapshot)
    db.flush()  # Flush to get snapshot.id before indicator insert

    # --- Technical Indicator Calculation (isolated: must never lose the price snapshot) ---
    _try_compute_and_store_indicator(db, asset=asset, source=source, snapshot=snapshot, observed_at=observed_at)

    # --- Option C: Replicate to XAG_GRAM (divided by 31.1035) ---
    if asset.symbol == "XAG":
        gram_asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
        if gram_asset:
            conversion_rate = Decimal("31.1035")
            gram_buy = _price(buy_price / conversion_rate)
            gram_sell = _price(sell_price / conversion_rate)
            gram_mid = _price(mid_price / conversion_rate)
            gram_spread_abs = _price(spread_absolute / conversion_rate)

            raw_gram = RawGlobalPrice(
                collector_run_id=run.id,
                asset_id=gram_asset.id,
                source=source,
                buy_price=gram_buy,
                sell_price=gram_sell,
                currency=currency.upper(),
                observed_at=observed_at,
                fetched_at=fetched_at,
                raw_payload_hash=raw_hash,
                parser_version=parser_version,
                payload_json=payload,
            )
            db.add(raw_gram)

            snapshot_gram = PriceSnapshot(
                collector_run_id=run.id,
                asset_id=gram_asset.id,
                source=source,
                buy_price=gram_buy,
                sell_price=gram_sell,
                mid_price=gram_mid,
                currency=currency.upper(),
                spread_absolute=gram_spread_abs,
                spread_percent=spread_percent,
                observed_at=observed_at,
                resolved_source=source,
                is_degraded=False,
            )
            db.add(snapshot_gram)
            db.flush()

            _try_compute_and_store_indicator(
                db, asset=gram_asset, source=source, snapshot=snapshot_gram, observed_at=observed_at
            )

    finish_collector_run(db, run, status="success", records_inserted=1)
    db.commit()
    db.refresh(run)
    db.refresh(snapshot)
    return run, True, snapshot


# ---------------------------------------------------------------------------
# Technical Indicator helper (Phase 3.6)
# ---------------------------------------------------------------------------
_INDICATOR_HISTORY_BARS = 200
_INDICATOR_GLOBAL_SOURCES = {"yahoo-si-f", "gold-api-xag-usd", "metals-dev-silver-spot"}
_MARKET_BAR_TIMEFRAME = "5m"
_MARKET_BAR_MINUTES = 5
_MARKET_BAR_BUILDER_VERSION = "market-bars-v1"
_INDICATOR_CALCULATION_VERSION = "technical-indicators-v1"


def _try_compute_and_store_indicator(
    db: Session,
    *,
    asset: Asset,
    source: str,
    snapshot: PriceSnapshot,
    observed_at: datetime,
) -> None:
    """Compute technical indicators for the latest global price bar.

    This function is intentionally isolated with try/except so that a failure
    in indicator calculation NEVER causes the parent price snapshot to be lost.
    Only triggers for global sources (yahoo-si-f), not bank sources.
    """
    if source not in _INDICATOR_GLOBAL_SOURCES:
        return

    try:
        bars = _ensure_recent_market_bars_from_snapshots(db, asset=asset, source=source)
        if not bars:
            logger.warning("indicator_skip: no market bars for asset_id=%s source=%s", asset.id, source)
            return

        records = []
        for bar in bars:
            records.append(
                {
                    "high": float(bar.high or bar.close or 0),
                    "low": float(bar.low or bar.close or 0),
                    "close": float(bar.close or 0),
                }
            )
        df = pd.DataFrame(records)

        # Calculate indicators
        df_ind = calculate_indicators(df)
        last = df_ind.iloc[-1]

        def _to_dec(val) -> Decimal | None:
            if pd.isna(val) or val is None:
                return None
            return Decimal(str(val)).quantize(PRICE_QUANT)

        indicator_values = {
            "price_snapshot_id": snapshot.id,
            "market_bar_id": bars[-1].id,
            "bar_timestamp": bars[-1].bar_start_at,
            "timeframe": _MARKET_BAR_TIMEFRAME,
            "calculation_version": _INDICATOR_CALCULATION_VERSION,
            "input_bar_count": len(bars),
            "quality_status": bars[-1].quality_status,
            "close_usd_oz": bars[-1].close,
            "rsi_14": _to_dec(last.get("rsi_14")),
            "macd_line": _to_dec(last.get("macd_line")),
            "macd_signal": _to_dec(last.get("macd_signal")),
            "macd_histogram": _to_dec(last.get("macd_histogram")),
            "bb_upper_20_2": _to_dec(last.get("bb_upper_20_2")),
            "bb_middle_20_2": _to_dec(last.get("bb_middle_20_2")),
            "bb_lower_20_2": _to_dec(last.get("bb_lower_20_2")),
            "sma_20": _to_dec(last.get("sma_20")),
            "sma_50": _to_dec(last.get("sma_50")),
            "sma_200": _to_dec(last.get("sma_200")),
            "atr_14": _to_dec(last.get("atr_14")),
            "xau_xag_ratio": None,
        }
        indicator = db.execute(
            select(TechnicalIndicator).where(
                TechnicalIndicator.market_bar_id == bars[-1].id,
                TechnicalIndicator.calculation_version == _INDICATOR_CALCULATION_VERSION,
            )
        ).scalar_one_or_none()
        if indicator is None:
            db.add(TechnicalIndicator(**indicator_values))
        else:
            for key, value in indicator_values.items():
                setattr(indicator, key, value)
        logger.info(
            "indicator_computed: snapshot_id=%s market_bar_id=%s rsi=%.2f sma20=%s",
            snapshot.id,
            bars[-1].id,
            float(last.get("rsi_14", 0) or 0),
            last.get("sma_20"),
        )
    except Exception:
        logger.exception(
            "indicator_error: failed to compute indicators for snapshot_id=%s — price snapshot preserved", snapshot.id
        )


def _ensure_recent_market_bars_from_snapshots(db: Session, *, asset: Asset, source: str) -> list[MarketBar]:
    latest_ids_sq = (
        select(PriceSnapshot.id)
        .where(
            PriceSnapshot.asset_id == asset.id,
            PriceSnapshot.source == source,
        )
        .order_by(desc(PriceSnapshot.observed_at), desc(PriceSnapshot.id))
        .limit(_INDICATOR_HISTORY_BARS * 3)
    ).subquery()
    snapshots = (
        db.execute(
            select(PriceSnapshot)
            .where(PriceSnapshot.id.in_(select(latest_ids_sq)))
            .order_by(PriceSnapshot.observed_at.asc(), PriceSnapshot.id.asc())
        )
        .scalars()
        .all()
    )
    if not snapshots:
        return []

    grouped: dict[datetime, list[PriceSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(_bar_start(snapshot.observed_at), []).append(snapshot)

    bars: list[MarketBar] = []
    for bar_start_at in sorted(grouped):
        group = sorted(grouped[bar_start_at], key=lambda item: (_aware(item.observed_at), item.id))
        first = group[0]
        last = group[-1]
        prices = [item.mid_price for item in group if item.mid_price is not None]
        if not prices:
            continue
        quality_status = "degraded" if any(item.is_degraded for item in group) else "ok"
        existing = db.execute(
            select(MarketBar).where(
                MarketBar.asset_id == asset.id,
                MarketBar.source == source,
                MarketBar.timeframe == _MARKET_BAR_TIMEFRAME,
                MarketBar.bar_start_at == bar_start_at,
            )
        ).scalar_one_or_none()
        values = {
            "bar_end_at": bar_start_at + timedelta(minutes=_MARKET_BAR_MINUTES),
            "open": _price(first.mid_price),
            "high": _price(max(prices)),
            "low": _price(min(prices)),
            "close": _price(last.mid_price),
            "currency": last.currency,
            "sample_count": len(group),
            "first_price_snapshot_id": first.id,
            "last_price_snapshot_id": last.id,
            "quality_status": quality_status,
            "bar_builder_version": _MARKET_BAR_BUILDER_VERSION,
        }
        if existing is None:
            existing = MarketBar(
                asset_id=asset.id,
                source=source,
                timeframe=_MARKET_BAR_TIMEFRAME,
                bar_start_at=bar_start_at,
                **values,
            )
            db.add(existing)
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        bars.append(existing)

    db.flush()
    return bars[-_INDICATOR_HISTORY_BARS:]


def _bar_start(value: datetime) -> datetime:
    aware_value = _aware(value)
    minute = aware_value.minute - (aware_value.minute % _MARKET_BAR_MINUTES)
    return aware_value.replace(minute=minute, second=0, microsecond=0)


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
    usd_buy_price: Decimal | None = None,
    usd_sell_price: Decimal | None = None,
    resolved_source: str | None = None,
    is_degraded: bool = False,
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
            resolved_source=resolved_source,
            is_degraded=is_degraded,
        )
    )

    snap_buy = usd_buy_price if usd_buy_price is not None else buy_price
    snap_sell = usd_sell_price if usd_sell_price is not None else sell_price
    snap_curr = "USD" if usd_buy_price is not None else currency.upper()

    spread_absolute = _price(snap_buy - snap_sell)
    mid_price = _price((snap_buy + snap_sell) / Decimal("2"))
    spread_percent = _price((spread_absolute / mid_price) * Decimal("100")) if mid_price > 0 else Decimal("0.000000")
    snapshot = PriceSnapshot(
        collector_run_id=run.id,
        asset_id=asset.id,
        source=source,
        buy_price=_price(snap_buy),
        sell_price=_price(snap_sell),
        mid_price=mid_price,
        currency=snap_curr,
        spread_absolute=spread_absolute,
        spread_percent=spread_percent,
        observed_at=observed_at,
        resolved_source=resolved_source,
        is_degraded=is_degraded,
    )
    db.add(snapshot)
    db.flush()

    # --- Option C: Replicate to XAG_GRAM (divided by 31.1035) ---
    if asset_symbol == "XAG":
        gram_asset = db.execute(select(Asset).where(Asset.symbol == "XAG_GRAM")).scalar_one_or_none()
        if gram_asset:
            conversion_rate = Decimal("31.1035")
            gram_snap_buy = _price(snap_buy / conversion_rate)
            gram_snap_sell = _price(snap_sell / conversion_rate)
            gram_snap_mid = _price(mid_price / conversion_rate)
            gram_spread_abs = _price(spread_absolute / conversion_rate)

            raw_gram = RawBankPrice(
                collector_run_id=run.id,
                asset_id=gram_asset.id,
                source=source,
                buy_price=_price(buy_price),
                sell_price=_price(sell_price),
                currency=currency.upper(),
                observed_at=observed_at,
                fetched_at=fetched_at,
                raw_payload_hash=payload_hash(raw_payload),
                parser_version=parser_version,
                payload_json=payload,
                resolved_source=resolved_source,
                is_degraded=is_degraded,
            )
            db.add(raw_gram)

            snapshot_gram = PriceSnapshot(
                collector_run_id=run.id,
                asset_id=gram_asset.id,
                source=source,
                buy_price=gram_snap_buy,
                sell_price=gram_snap_sell,
                mid_price=gram_snap_mid,
                currency=snap_curr,
                spread_absolute=gram_spread_abs,
                spread_percent=spread_percent,
                observed_at=observed_at,
                resolved_source=resolved_source,
                is_degraded=is_degraded,
            )
            db.add(snapshot_gram)
            db.flush()

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
    if collector_name == "yahoo_usd_try":
        latest_tcmb = db.execute(
            select(RawFxRate)
            .where(
                RawFxRate.source == "tcmb-today-xml",
                RawFxRate.base_currency == "USD",
                RawFxRate.quote_currency == "TRY",
            )
            .order_by(RawFxRate.observed_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if latest_tcmb:
            deviation = abs(rate - latest_tcmb.rate) / latest_tcmb.rate
            if deviation >= Decimal("0.02"):
                import logging

                logger = logging.getLogger(__name__)
                logger.warning("USD/TRY deviation >= 2% compared to TCMB daily reference")

                if "warning" not in run.details_json:
                    details = dict(run.details_json)
                    details["warning"] = "USD/TRY deviation >= 2% compared to TCMB daily reference"
                    details["yahoo_rate"] = str(rate)
                    details["tcmb_rate"] = str(latest_tcmb.rate)
                    details["deviation_pct"] = float(deviation)
                    run.details_json = details

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


def ingest_event_items(
    db: Session,
    *,
    collector_name: str,
    source: str,
    event_type: str,
    items: list[dict],
    fetched_at: datetime,
    parser_version: str,
) -> tuple[CollectorRun, int]:
    fetched_at = _utc(fetched_at)
    source = source.lower()
    run = start_collector_run(
        db,
        collector_name=collector_name,
        source=source,
        records_seen=len(items),
        details_json={"parser_version": parser_version},
    )
    inserted = 0
    duplicates = 0
    for item in items:
        observed_at = item.get("observed_at")
        if not isinstance(observed_at, datetime):
            raise CollectorError("Event item observed_at is required")
        observed_at = _utc(observed_at)

        payload = dict(item)
        payload["observed_at"] = observed_at.isoformat()
        raw_hash = payload_hash(payload)
        duplicate = db.execute(
            select(RawEvent).where(
                RawEvent.source == source,
                RawEvent.event_type == event_type,
                RawEvent.observed_at == observed_at,
                RawEvent.raw_payload_hash == raw_hash,
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            duplicates += 1
            continue

        db.add(
            RawEvent(
                collector_run_id=run.id,
                source=source,
                event_type=event_type,
                payload_json=payload,
                observed_at=observed_at,
                fetched_at=fetched_at,
                raw_payload_hash=raw_hash,
                parser_version=parser_version,
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


def collector_health(db: Session, stale_after_minutes: int = 60, *, now: datetime | None = None) -> dict:
    from sqlalchemy import func

    ranked_runs = select(
        CollectorRun.id,
        func.row_number()
        .over(
            partition_by=(CollectorRun.collector_name, CollectorRun.source),
            order_by=(desc(CollectorRun.started_at), desc(CollectorRun.id)),
        )
        .label("rn"),
    ).subquery()
    runs = (
        db.execute(
            select(CollectorRun)
            .where(CollectorRun.id.in_(select(ranked_runs.c.id).where(ranked_runs.c.rn == 1)))
            .order_by(CollectorRun.started_at.desc())
        )
        .scalars()
        .all()
    )

    active_run_sources = _active_collector_run_sources()
    latest_by_collector: dict[tuple[str, str], CollectorRun] = {}
    for run in runs:
        if not _is_active_collector_run(run.collector_name, run.source, active_run_sources):
            continue
        key = (run.collector_name, run.source)
        if key not in latest_by_collector:
            latest_by_collector[key] = run

    stale_after_seconds = stale_after_minutes * 60
    now = now or datetime.now(UTC)
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

    bank_price = _execution_critical_bank_price_status(db, stale_after_seconds=stale_after_seconds, now=now)
    global_xag = _execution_critical_global_xag_status(db, stale_after_seconds=stale_after_seconds, now=now)
    usd_try = _execution_critical_usd_try_status(db, stale_after_seconds=stale_after_seconds, now=now)
    execution_critical_status = _execution_critical_status(bank_price, global_xag, usd_try)
    context_status = _context_status(collectors)
    any_problem = any(
        (item["stale"] or item["status"] == "failed")
        and not _ignore_inactive_manual_fallback(item, bank_price=bank_price)
        for item in collectors
    )
    if not collectors:
        status = "empty"
    elif execution_critical_status == "blocked":
        status = "blocked"
    elif execution_critical_status == "stale":
        status = "stale"
    elif execution_critical_status == "degraded" or any_problem:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "execution_critical_status": execution_critical_status,
        "context_status": context_status,
        "execution_critical": {
            **bank_price,
            "global_xag_usd": global_xag["global_xag_usd"],
            "global_xag_source": global_xag["source"],
            "selected_global_xag_source": global_xag["source"],
            "global_xag_age_seconds": global_xag["age_seconds"],
            "observed_age_seconds": global_xag.get("observed_age_seconds"),
            "global_xag_stale": global_xag["stale"],
            "global_xag_manual_fallback": global_xag["manual_fallback"],
            "usd_try": usd_try["usd_try"],
            "usd_try_source": usd_try["source"],
            "usd_try_age_seconds": usd_try["age_seconds"],
            "usd_try_stale": usd_try["stale"],
        },
        "stale_after_minutes": stale_after_minutes,
        "collectors": collectors,
    }


def collector_quality(db: Session, *, window_hours: int = 24, expected_interval_minutes: int = 60) -> dict:
    if window_hours <= 0:
        raise CollectorError("window_hours must be greater than zero")
    if expected_interval_minutes <= 0:
        raise CollectorError("expected_interval_minutes must be greater than zero")

    now = datetime.now(UTC)
    since = now - timedelta(hours=window_hours)
    expected_runs = max(1, int((window_hours * 60) / expected_interval_minutes))
    runs = (
        db.execute(
            select(CollectorRun).where(CollectorRun.started_at >= since).order_by(CollectorRun.started_at.desc())
        )
        .scalars()
        .all()
    )

    groups: dict[tuple[str, str], list[CollectorRun]] = {}
    active_run_sources = _active_collector_run_sources()
    for run in runs:
        if not _is_active_collector_run(run.collector_name, run.source, active_run_sources):
            continue
        groups.setdefault((run.collector_name, run.source), []).append(run)
    has_non_manual_group = any(not _is_manual_fallback_group(*key) for key in groups)
    quality_group_keys = {key for key in groups if not (has_non_manual_group and _is_manual_fallback_group(*key))}

    window_started_at = _quality_window_started_at(db, quality_group_keys)
    elapsed_minutes = (
        min(window_hours * 60, max(0, int((now - window_started_at).total_seconds() / 60)))
        if window_started_at is not None
        else 0
    )
    expected_runs_so_far = 0
    if runs:
        expected_runs_so_far = max(1, int(elapsed_minutes / expected_interval_minutes) + 1)
        expected_runs_so_far = min(expected_runs_so_far, expected_runs)
    validation_window_complete = elapsed_minutes >= window_hours * 60

    collectors = []
    for (collector_name, source), collector_runs in groups.items():
        if has_non_manual_group and _is_manual_fallback_group(collector_name, source):
            continue
        total_runs = len(collector_runs)
        successful_runs = sum(1 for run in collector_runs if run.status == "success")
        failed_runs = sum(1 for run in collector_runs if run.status == "failed")
        records_seen = sum(run.records_seen for run in collector_runs)
        records_inserted = sum(run.records_inserted for run in collector_runs)
        duplicates = sum(run.duplicates for run in collector_runs)
        missing_runs = max(expected_runs_so_far - total_runs, 0)
        latest = collector_runs[0]
        collectors.append(
            {
                "collector_name": collector_name,
                "source": source,
                "runs": total_runs,
                "successful_runs": successful_runs,
                "failed_runs": failed_runs,
                "records_seen": records_seen,
                "records_inserted": records_inserted,
                "duplicates": duplicates,
                "failure_ratio": _ratio(failed_runs, total_runs),
                "duplicate_ratio": _ratio(duplicates, records_seen),
                "missing_runs": missing_runs,
                "missing_ratio": _ratio(missing_runs, expected_runs),
                "latest_status": latest.status,
                "latest_finished_at": latest.finished_at,
            }
        )

    if not collectors:
        status = "empty"
    elif any(item["failed_runs"] or item["missing_runs"] for item in collectors):
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "window_hours": window_hours,
        "window_started_at": window_started_at,
        "elapsed_minutes": elapsed_minutes,
        "validation_window_complete": validation_window_complete,
        "expected_interval_minutes": expected_interval_minutes,
        "expected_runs_per_collector": expected_runs,
        "expected_runs_so_far_per_collector": expected_runs_so_far,
        "collectors": collectors,
    }


def collector_validation_gate(
    db: Session,
    *,
    window_hours: int = 24,
    expected_interval_minutes: int = 15,
    stale_after_minutes: int = 60,
) -> dict:
    health = collector_health(db, stale_after_minutes=stale_after_minutes)
    quality = collector_quality(db, window_hours=window_hours, expected_interval_minutes=expected_interval_minutes)

    blocking_reasons = []
    degraded_reasons = []
    if health["execution_critical"]["bank_price"] != "fresh":
        blocking_reasons.append("EXECUTION_CRITICAL_BANK_PRICE_NOT_FRESH")
    if health["execution_critical"]["global_xag_usd"] not in {"fresh", "manual_fallback"}:
        blocking_reasons.append("EXECUTION_CRITICAL_GLOBAL_XAG_NOT_FRESH")
    if health["execution_critical"]["usd_try"] != "fresh":
        blocking_reasons.append("EXECUTION_CRITICAL_USD_TRY_NOT_FRESH")
    if not quality["validation_window_complete"]:
        blocking_reasons.append("VALIDATION_WINDOW_INCOMPLETE")

    context_quality_items = [item for item in quality["collectors"] if item["collector_name"] in CONTEXT_COLLECTORS]
    if quality["status"] != "ok":
        degraded_reasons.append("QUALITY_STATUS_NOT_OK")
    if health["status"] != "healthy":
        degraded_reasons.append("COLLECTOR_HEALTH_NOT_HEALTHY")
    if any(item["failed_runs"] > 0 for item in quality["collectors"]):
        degraded_reasons.append("COLLECTOR_FAILURES_PRESENT")
    if any(item["missing_runs"] > 0 for item in quality["collectors"]):
        degraded_reasons.append("MISSING_RUNS_PRESENT")
    if any(item["failed_runs"] > 0 for item in context_quality_items):
        degraded_reasons.append("CONTEXT_COLLECTOR_FAILURES_PRESENT")
    if any(item["missing_runs"] > 0 for item in context_quality_items):
        degraded_reasons.append("CONTEXT_MISSING_RUNS_PRESENT")

    source_reliability = _source_reliability_summary(quality["collectors"])
    stooq_timeout_count = _stooq_timeout_count(db, window_hours=window_hours)
    provider_failure_counts = _provider_failure_counts(db, window_hours=window_hours)

    if not health["collectors"] and not quality["collectors"]:
        status = "empty"
    elif any(reason != "VALIDATION_WINDOW_INCOMPLETE" for reason in blocking_reasons):
        status = "blocked"
    elif "VALIDATION_WINDOW_INCOMPLETE" in blocking_reasons:
        status = "warming_up"
    else:
        status = "ready"
        blocking_reasons = ["READY"]

    return {
        "status": status,
        "phase4_allowed": status == "ready",
        "reasons": blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "degraded_reasons": sorted(set(degraded_reasons)),
        "health_status": health["status"],
        "quality_status": quality["status"],
        "execution_critical_status": health["execution_critical_status"],
        "context_status": health["context_status"],
        "source_reliability": source_reliability,
        "stooq_xag_usd_timeout_count": stooq_timeout_count,
        "provider_failure_counts": provider_failure_counts,
        "selected_global_xag_source": health["execution_critical"]["selected_global_xag_source"],
        "window_hours": quality["window_hours"],
        "elapsed_minutes": quality["elapsed_minutes"],
        "validation_window_complete": quality["validation_window_complete"],
        "expected_interval_minutes": quality["expected_interval_minutes"],
        "expected_runs_per_collector": quality["expected_runs_per_collector"],
        "expected_runs_so_far_per_collector": quality["expected_runs_so_far_per_collector"],
    }


def _execution_critical_bank_price_status(db: Session, *, stale_after_seconds: int, now: datetime) -> dict:
    latest_bank_price = db.execute(
        select(RawBankPrice).order_by(desc(RawBankPrice.fetched_at), desc(RawBankPrice.observed_at)).limit(1)
    ).scalar_one_or_none()
    if latest_bank_price is None:
        return {
            "bank_price": "missing",
            "source": None,
            "age_seconds": None,
            "stale": True,
            "manual_fallback": False,
        }

    reference_time = _aware(latest_bank_price.fetched_at or latest_bank_price.observed_at)
    age_seconds = int((now - reference_time).total_seconds()) if reference_time is not None else None
    stale = age_seconds is None or age_seconds > stale_after_seconds
    manual_fallback = latest_bank_price.parser_version == "manual-v1" or latest_bank_price.source.startswith("manual")
    if stale:
        bank_price = "stale"
    elif manual_fallback:
        bank_price = "manual_fallback"
    else:
        bank_price = "fresh"
    return {
        "bank_price": bank_price,
        "source": latest_bank_price.source,
        "age_seconds": age_seconds,
        "stale": stale,
        "manual_fallback": manual_fallback,
    }


def _execution_critical_global_xag_status(db: Session, *, stale_after_seconds: int, now: datetime) -> dict:
    settings = get_settings()
    asset = db.execute(select(Asset).where(Asset.symbol.in_(["XAG_GRAM", "XAG"]))).scalars().first()
    if asset is None:
        latest_global_price = None
    else:
        latest_global_price = db.execute(
            select(RawGlobalPrice)
            .where(RawGlobalPrice.asset_id == asset.id)
            .order_by(desc(RawGlobalPrice.fetched_at), desc(RawGlobalPrice.observed_at))
            .limit(1)
        ).scalar_one_or_none()
    if latest_global_price is None:
        return {
            "global_xag_usd": "missing",
            "source": None,
            "age_seconds": None,
            "stale": True,
            "manual_fallback": False,
        }

    latest_success_time = _latest_successful_run_time(
        db,
        collector_names={"global_xag_usd", "gold_api_xag_usd", "metals_dev_silver_spot", "stooq_xag_usd"},
        source=latest_global_price.source,
    )
    reference_time = max(
        value
        for value in (
            _aware(latest_global_price.fetched_at or latest_global_price.observed_at),
            latest_success_time,
        )
        if value is not None
    )
    observed_time = _aware(latest_global_price.observed_at)
    age_seconds = int((now - reference_time).total_seconds()) if reference_time is not None else None
    observed_age_seconds = int((now - observed_time).total_seconds()) if observed_time is not None else None
    stale_after = min(stale_after_seconds, settings.global_xag_freshness_minutes * 60)
    stale = (
        age_seconds is None
        or age_seconds > stale_after
        or observed_age_seconds is None
        or observed_age_seconds > stale_after
    )
    manual_fallback = latest_global_price.parser_version == "manual-v1" or latest_global_price.source.startswith(
        "manual"
    )
    if stale:
        global_xag = "stale"
    elif manual_fallback:
        global_xag = "manual_fallback"
    else:
        global_xag = "fresh"
    return {
        "global_xag_usd": global_xag,
        "source": latest_global_price.source,
        "age_seconds": age_seconds,
        "observed_age_seconds": observed_age_seconds,
        "stale": stale,
        "manual_fallback": manual_fallback,
    }


def _execution_critical_usd_try_status(db: Session, *, stale_after_seconds: int, now: datetime) -> dict:
    latest_fx_rate = db.execute(
        select(RawFxRate)
        .where(RawFxRate.base_currency == "USD", RawFxRate.quote_currency == "TRY")
        .order_by(desc(RawFxRate.fetched_at), desc(RawFxRate.observed_at))
        .limit(1)
    ).scalar_one_or_none()
    if latest_fx_rate is None:
        return {"usd_try": "missing", "source": None, "age_seconds": None, "stale": True}

    latest_success_time = _latest_successful_run_time(
        db, collector_names={"tcmb_usd_try", "yahoo_usd_try", "kuveyt_usd_try"}, source=latest_fx_rate.source
    )
    reference_time = max(
        value
        for value in (
            _aware(latest_fx_rate.fetched_at or latest_fx_rate.observed_at),
            latest_success_time,
        )
        if value is not None
    )
    age_seconds = int((now - reference_time).total_seconds()) if reference_time is not None else None
    stale = age_seconds is None or age_seconds > stale_after_seconds
    return {
        "usd_try": "stale" if stale else "fresh",
        "source": latest_fx_rate.source,
        "age_seconds": age_seconds,
        "stale": stale,
    }


def _execution_critical_status(bank_price: dict, global_xag: dict, usd_try: dict) -> str:
    statuses = (bank_price["bank_price"], global_xag["global_xag_usd"], usd_try["usd_try"])
    if any(status == "missing" for status in statuses):
        return "blocked"
    if any(status == "stale" for status in statuses):
        return "stale"
    if any(status == "manual_fallback" for status in statuses):
        return "degraded"
    return "healthy"


def _context_status(collectors: list[dict]) -> str:
    context_items = [item for item in collectors if item["collector_name"] in CONTEXT_COLLECTORS]
    if not context_items:
        return "empty"
    if any(item["stale"] or item["status"] == "failed" for item in context_items):
        return "degraded"
    return "healthy"


def _source_reliability_summary(collectors: list[dict]) -> list[dict]:
    summary = []
    for item in collectors:
        runs = item["runs"]
        successful_runs = item["successful_runs"]
        reliability_score = _ratio(successful_runs, runs)
        summary.append(
            {
                "collector_name": item["collector_name"],
                "source": item["source"],
                "runs": runs,
                "successful_runs": successful_runs,
                "failed_runs": item["failed_runs"],
                "missing_runs": item["missing_runs"],
                "reliability_score": reliability_score,
            }
        )
    return summary


def _active_collector_run_sources() -> dict[str, set[str]]:
    jobs = [job.strip() for job in os.getenv("COLLECTOR_JOBS", DEFAULT_COLLECTOR_JOBS).split(",") if job.strip()]
    if not jobs:
        fallback_job = os.getenv("COLLECTOR_JOB", "").strip()
        jobs = [fallback_job] if fallback_job else []

    active: dict[str, set[str]] = {}
    for job in jobs:
        if job == "global-xag-usd":
            active.setdefault("global_xag_usd", set()).update(_active_global_xag_sources())
            active["global_xag_usd"].add("global-xag-usd-resolver")
            continue
        for collector_name, sources in COLLECTOR_JOB_RUN_SOURCES.get(job, {}).items():
            active.setdefault(collector_name, set()).update(sources)
    return active


def _active_global_xag_sources() -> set[str]:
    settings = get_settings()
    sources = set()
    for raw_source in settings.global_xag_source_priority.split(","):
        source = raw_source.strip().lower()
        if not source:
            continue
        sources.add(GLOBAL_XAG_SOURCE_ALIASES.get(source, source))
    return sources


def _is_active_collector_run(collector_name: str, source: str, active_run_sources: dict[str, set[str]]) -> bool:
    if _is_manual_fallback_group(collector_name, source):
        return True
    return source in active_run_sources.get(collector_name, set())


def _stooq_timeout_count(db: Session, *, window_hours: int) -> int:
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    runs = db.execute(
        select(CollectorRun).where(
            CollectorRun.collector_name == "stooq_xag_usd",
            CollectorRun.started_at >= since,
        )
    ).scalars()
    count = 0
    for run in runs:
        details = run.details_json or {}
        if details.get("failure_reason_code") == "TIMEOUT":
            count += 1
    return count


def _provider_failure_counts(db: Session, *, window_hours: int) -> dict[str, int]:
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    active_run_sources = _active_collector_run_sources()
    runs = db.execute(
        select(CollectorRun).where(
            CollectorRun.status == "failed",
            CollectorRun.started_at >= since,
        )
    ).scalars()
    counts: dict[str, int] = {}
    for run in runs:
        if not _is_active_collector_run(run.collector_name, run.source, active_run_sources):
            continue
        counts[run.collector_name] = counts.get(run.collector_name, 0) + 1
    return counts


def _latest_successful_run_time(db: Session, *, collector_names: set[str], source: str) -> datetime | None:
    run = db.execute(
        select(CollectorRun)
        .where(
            CollectorRun.collector_name.in_(collector_names),
            CollectorRun.source == source,
            CollectorRun.status == "success",
        )
        .order_by(desc(CollectorRun.finished_at), desc(CollectorRun.started_at))
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        return None
    return _aware(run.finished_at or run.started_at)


def _ignore_inactive_manual_fallback(item: dict, *, bank_price: dict) -> bool:
    if bank_price["bank_price"] != "fresh":
        return False
    return _is_manual_fallback_group(item["collector_name"], item["source"])


def _quality_window_started_at(db: Session, quality_group_keys: set[tuple[str, str]]) -> datetime | None:
    if not quality_group_keys:
        return None

    runs = db.execute(select(CollectorRun).order_by(CollectorRun.started_at.asc())).scalars()
    for run in runs:
        if (run.collector_name, run.source) in quality_group_keys:
            return _aware(run.started_at)
    return None


def _is_manual_fallback_group(collector_name: str, source: str) -> bool:
    return collector_name.startswith("manual_") or source.startswith("manual")


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


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)
