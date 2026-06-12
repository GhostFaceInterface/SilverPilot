import os
import sys
import json
import argparse
import httpx
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pandas as pd

# Path setup to import app modules
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
api_path = os.path.join(root_path, "apps", "api")
if os.path.exists(api_path):
    if api_path not in sys.path:
        sys.path.insert(0, api_path)
elif os.path.exists(os.path.join(root_path, "app")):
    if root_path not in sys.path:
        sys.path.insert(0, root_path)

from app.core.db import SessionLocal  # noqa: E402
from app.models import Asset, CollectorRun, PriceSnapshot, RawGlobalPrice, TechnicalIndicator, MarketBar  # noqa: E402
from app.services.indicators import calculate_indicators  # noqa: E402


def fetch_yahoo_daily_history() -> pd.DataFrame:
    # Fetch 2 years of daily data from Yahoo Finance
    url = "https://query1.finance.yahoo.com/v8/finance/chart/SI=F"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    params = {"range": "2y", "interval": "1d"}

    print("Fetching 2 years of daily data from Yahoo Finance...")
    response = httpx.get(url, params=params, headers=headers, timeout=30.0)
    response.raise_for_status()
    body = response.json()

    chart = body.get("chart") or {}
    result_list = chart.get("result")
    if not result_list:
        raise ValueError("No result returned from Yahoo Finance API")

    result = result_list[0]
    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or []
    if not quotes:
        raise ValueError("No quote data returned from Yahoo Finance API")

    quote = quotes[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    records = []
    for i in range(len(timestamps)):
        t = timestamps[i]
        c = closes[i]
        if t is None or c is None:
            continue
        o = opens[i] if i < len(opens) and opens[i] is not None else c
        h = highs[i] if i < len(highs) and highs[i] is not None else c
        low = lows[i] if i < len(lows) and lows[i] is not None else c
        v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0

        records.append(
            {
                "timestamp": int(t),
                "open": float(o),
                "high": float(h),
                "low": float(low),
                "close": float(c),
                "volume": float(v),
            }
        )

    df = pd.DataFrame(records)
    return df.sort_values("timestamp").reset_index(drop=True)


def backfill(
    *,
    dry_run: bool = False,
    assets: list[str] | None = None,
    timeframes: list[str] | None = None,
    min_bars: int = 60,
):
    asset_filter = set(assets or ["XAG", "XAG_GRAM"])
    timeframe_filter = set(timeframes or ["1d"])
    if timeframe_filter != {"1d"}:
        raise ValueError("backfill_history currently supports only the 1d timeframe")
    if not asset_filter.issubset({"XAG", "XAG_GRAM"}):
        raise ValueError("backfill_history currently supports only XAG and XAG_GRAM")

    df = fetch_yahoo_daily_history()
    print(f"Loaded {len(df)} price bars from Yahoo Finance. Calculating indicators...")
    if len(df) < min_bars:
        raise ValueError(f"Yahoo returned {len(df)} bars, below required minimum {min_bars}")

    if dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "assets": sorted(asset_filter),
                    "timeframes": sorted(timeframe_filter),
                    "loaded_bars": len(df),
                    "min_bars": min_bars,
                },
                sort_keys=True,
            )
        )
        return

    db = SessionLocal()
    run = None
    try:
        # 1. Fetch Asset
        asset_xag = db.query(Asset).filter(Asset.symbol == "XAG").first()
        if not asset_xag:
            print("XAG Asset not found. Creating it...")
            asset_xag = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
            db.add(asset_xag)
            db.commit()
            db.refresh(asset_xag)

        asset_gram = db.query(Asset).filter(Asset.symbol == "XAG_GRAM").first()
        if not asset_gram:
            print("XAG_GRAM Asset not found. Creating it...")
            asset_gram = Asset(symbol="XAG_GRAM", name="Silver Gram Spot", asset_type="metal", is_active=True)
            db.add(asset_gram)
            db.commit()
            db.refresh(asset_gram)

        print(f"XAG Asset ID: {asset_xag.id}, XAG_GRAM Asset ID: {asset_gram.id}")

        # 2. Start Collector Run
        run = CollectorRun(
            collector_name="yahoo_xag_usd_backfill",
            source="yahoo-si-f",
            status="running",
            records_seen=0,
            records_inserted=0,
            duplicates=0,
            details_json={"asset_symbols": ["XAG", "XAG_GRAM"]},
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        # Calculate technical indicators
        df_indicators = calculate_indicators(df)

        # Pre-fetch existing observed_at timestamps from PriceSnapshot (Phase 2 optimization)
        print("Pre-fetching existing PriceSnapshot timestamps...")
        existing_snapshots_xag = set(
            (r[0].replace(tzinfo=UTC) if r[0].tzinfo is None else r[0].astimezone(UTC))
            for r in db.query(PriceSnapshot.observed_at)
            .filter(PriceSnapshot.asset_id == asset_xag.id, PriceSnapshot.source == "yahoo-si-f")
            .all()
            if r[0] is not None
        )
        existing_snapshots_gram = set(
            (r[0].replace(tzinfo=UTC) if r[0].tzinfo is None else r[0].astimezone(UTC))
            for r in db.query(PriceSnapshot.observed_at)
            .filter(PriceSnapshot.asset_id == asset_gram.id, PriceSnapshot.source == "yahoo-si-f")
            .all()
            if r[0] is not None
        )
        print(
            f"Found {len(existing_snapshots_xag)} XAG and {len(existing_snapshots_gram)} XAG_GRAM existing PriceSnapshots."
        )

        # Pre-fetch existing observed_at timestamps from RawGlobalPrice (Phase 3 uniqueness check)
        print("Pre-fetching existing RawGlobalPrice timestamps...")
        existing_raws_xag = set(
            (r[0].replace(tzinfo=UTC) if r[0].tzinfo is None else r[0].astimezone(UTC))
            for r in db.query(RawGlobalPrice.observed_at)
            .filter(RawGlobalPrice.asset_id == asset_xag.id, RawGlobalPrice.source == "yahoo-si-f")
            .all()
            if r[0] is not None
        )
        existing_raws_gram = set(
            (r[0].replace(tzinfo=UTC) if r[0].tzinfo is None else r[0].astimezone(UTC))
            for r in db.query(RawGlobalPrice.observed_at)
            .filter(RawGlobalPrice.asset_id == asset_gram.id, RawGlobalPrice.source == "yahoo-si-f")
            .all()
            if r[0] is not None
        )
        print(f"Found {len(existing_raws_xag)} XAG and {len(existing_raws_gram)} XAG_GRAM existing RawGlobalPrices.")

        # Insert records
        seen = 0
        inserted = 0
        duplicates = 0

        for idx, row in df_indicators.iterrows():
            seen += 1
            observed_at = datetime.fromtimestamp(int(row["timestamp"]), tz=UTC)

            is_dup_xag = observed_at in existing_snapshots_xag or observed_at in existing_raws_xag
            is_dup_gram = observed_at in existing_snapshots_gram or observed_at in existing_raws_gram

            if is_dup_xag and is_dup_gram:
                duplicates += 1
                continue

            # Clean row values for JSON serialization (handling NaN and numpy types)
            payload_dict = {}
            for k, val in dict(row).items():
                if pd.isna(val):
                    payload_dict[k] = None
                elif hasattr(val, "item"):
                    item_val = val.item()
                    payload_dict[k] = None if pd.isna(item_val) else item_val
                else:
                    payload_dict[k] = val

            # Helper to convert float to Decimal safely
            def to_dec(val):
                if pd.isna(val) or val is None:
                    return None
                return Decimal(str(val))

            # 1. Process XAG if not duplicate
            if "XAG" in asset_filter and not is_dup_xag:
                close_price_xag = Decimal(str(row["close"]))

                # Create RawGlobalPrice
                raw_global_xag = RawGlobalPrice(
                    collector_run_id=run.id,
                    asset_id=asset_xag.id,
                    source="yahoo-si-f",
                    buy_price=close_price_xag,
                    sell_price=close_price_xag,
                    currency="USD",
                    observed_at=observed_at,
                    fetched_at=datetime.now(UTC),
                    raw_payload_hash="backfill_" + str(row["timestamp"]),
                    parser_version="yahoo-finance-chart-v1",
                    payload_json=payload_dict,
                )
                db.add(raw_global_xag)
                db.flush()

                # Create PriceSnapshot
                snap_xag = PriceSnapshot(
                    asset_id=asset_xag.id,
                    source="yahoo-si-f",
                    buy_price=close_price_xag,
                    sell_price=close_price_xag,
                    mid_price=close_price_xag,
                    currency="USD",
                    spread_absolute=Decimal("0.0"),
                    spread_percent=Decimal("0.0"),
                    observed_at=observed_at,
                    resolved_source="yahoo_si_f",
                    is_degraded=False,
                )
                db.add(snap_xag)
                db.flush()

                bar_xag = upsert_daily_market_bar(
                    db,
                    asset=asset_xag,
                    source="yahoo-si-f",
                    observed_at=observed_at,
                    open_price=Decimal(str(row["open"])),
                    high_price=Decimal(str(row["high"])),
                    low_price=Decimal(str(row["low"])),
                    close_price=close_price_xag,
                    snapshot_id=snap_xag.id,
                )

                # Create TechnicalIndicator
                ti_xag = TechnicalIndicator(
                    price_snapshot_id=snap_xag.id,
                    market_bar_id=bar_xag.id,
                    bar_timestamp=observed_at,
                    timeframe="1d",
                    calculation_version="technical-indicators-v2",
                    input_bar_count=idx + 1,
                    quality_status="ok",
                    close_usd_oz=close_price_xag,
                    rsi_14=to_dec(row.get("rsi_14")),
                    macd_line=to_dec(row.get("macd_line")),
                    macd_signal=to_dec(row.get("macd_signal")),
                    macd_histogram=to_dec(row.get("macd_histogram")),
                    bb_upper_20_2=to_dec(row.get("bb_upper_20_2")),
                    bb_middle_20_2=to_dec(row.get("bb_middle_20_2")),
                    bb_lower_20_2=to_dec(row.get("bb_lower_20_2")),
                    sma_20=to_dec(row.get("sma_20")),
                    sma_50=to_dec(row.get("sma_50")),
                    sma_200=to_dec(row.get("sma_200")),
                    atr_14=to_dec(row.get("atr_14")),
                    xau_xag_ratio=None,
                )
                db.add(ti_xag)
                existing_snapshots_xag.add(observed_at)
                existing_raws_xag.add(observed_at)
                inserted += 1

            # 2. Process XAG_GRAM if not duplicate
            if "XAG_GRAM" in asset_filter and not is_dup_gram:
                conversion_rate = Decimal("31.1035")
                close_price_xag = Decimal(str(row["close"]))
                close_price_gram = close_price_xag / conversion_rate

                def to_dec_gram(val):
                    dec_val = to_dec(val)
                    if dec_val is None:
                        return None
                    return dec_val / conversion_rate

                # Create RawGlobalPrice
                raw_global_gram = RawGlobalPrice(
                    collector_run_id=run.id,
                    asset_id=asset_gram.id,
                    source="yahoo-si-f",
                    buy_price=close_price_gram,
                    sell_price=close_price_gram,
                    currency="USD",
                    observed_at=observed_at,
                    fetched_at=datetime.now(UTC),
                    raw_payload_hash="backfill_gram_" + str(row["timestamp"]),
                    parser_version="yahoo-finance-chart-v1",
                    payload_json=payload_dict,
                )
                db.add(raw_global_gram)
                db.flush()

                # Create PriceSnapshot
                snap_gram = PriceSnapshot(
                    asset_id=asset_gram.id,
                    source="yahoo-si-f",
                    buy_price=close_price_gram,
                    sell_price=close_price_gram,
                    mid_price=close_price_gram,
                    currency="USD",
                    spread_absolute=Decimal("0.0"),
                    spread_percent=Decimal("0.0"),
                    observed_at=observed_at,
                    resolved_source="yahoo_si_f",
                    is_degraded=False,
                )
                db.add(snap_gram)
                db.flush()

                bar_gram = upsert_daily_market_bar(
                    db,
                    asset=asset_gram,
                    source="yahoo-si-f",
                    observed_at=observed_at,
                    open_price=Decimal(str(row["open"])) / conversion_rate,
                    high_price=Decimal(str(row["high"])) / conversion_rate,
                    low_price=Decimal(str(row["low"])) / conversion_rate,
                    close_price=close_price_gram,
                    snapshot_id=snap_gram.id,
                )

                # Create TechnicalIndicator
                ti_gram = TechnicalIndicator(
                    price_snapshot_id=snap_gram.id,
                    market_bar_id=bar_gram.id,
                    bar_timestamp=observed_at,
                    timeframe="1d",
                    calculation_version="technical-indicators-v2",
                    input_bar_count=idx + 1,
                    quality_status="ok",
                    close_usd_oz=close_price_gram,
                    rsi_14=to_dec(row.get("rsi_14")),
                    macd_line=to_dec_gram(row.get("macd_line")),
                    macd_signal=to_dec_gram(row.get("macd_signal")),
                    macd_histogram=to_dec_gram(row.get("macd_histogram")),
                    bb_upper_20_2=to_dec_gram(row.get("bb_upper_20_2")),
                    bb_middle_20_2=to_dec_gram(row.get("bb_middle_20_2")),
                    bb_lower_20_2=to_dec_gram(row.get("bb_lower_20_2")),
                    sma_20=to_dec_gram(row.get("sma_20")),
                    sma_50=to_dec_gram(row.get("sma_50")),
                    sma_200=to_dec_gram(row.get("sma_200")),
                    atr_14=to_dec_gram(row.get("atr_14")),
                    xau_xag_ratio=None,
                )
                db.add(ti_gram)
                existing_snapshots_gram.add(observed_at)
                existing_raws_gram.add(observed_at)
                inserted += 1

            if inserted % 100 == 0:
                db.commit()
                print(f"Processed {seen}/{len(df)} records. Inserted: {inserted}, Duplicates: {duplicates}")

        db.commit()

        # Finish run
        run.status = "success"
        run.records_seen = seen
        run.records_inserted = inserted
        run.duplicates = duplicates
        run.finished_at = datetime.now(UTC)
        db.commit()
        print("\nBackfill completed successfully!")
        print(f"Total processed: {seen}")
        print(f"Total inserted: {inserted}")
        print(f"Total duplicates skipped: {duplicates}")

    except Exception as exc:
        db.rollback()
        print(f"Backfill failed: {exc}", file=sys.stderr)
        try:
            if run is not None:
                run.status = "failed"
                run.error_message = str(exc)
                run.finished_at = datetime.now(UTC)
                db.add(run)
                db.commit()
        except Exception as commit_exc:
            print(f"Failed to record failed status in DB: {commit_exc}", file=sys.stderr)
        raise exc
    finally:
        db.close()


def upsert_daily_market_bar(
    db,
    *,
    asset: Asset,
    source: str,
    observed_at: datetime,
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
    snapshot_id: int,
) -> MarketBar:
    bar_start = observed_at.replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (
        db.query(MarketBar)
        .filter(
            MarketBar.asset_id == asset.id,
            MarketBar.source == source,
            MarketBar.timeframe == "1d",
            MarketBar.bar_start_at == bar_start,
        )
        .one_or_none()
    )
    values = {
        "bar_end_at": bar_start + timedelta(days=1),
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "currency": "USD",
        "sample_count": 1,
        "first_price_snapshot_id": snapshot_id,
        "last_price_snapshot_id": snapshot_id,
        "quality_status": "ok",
        "bar_builder_version": "market-bars-v1",
    }
    if existing is None:
        existing = MarketBar(
            asset_id=asset.id,
            source=source,
            timeframe="1d",
            bar_start_at=bar_start,
            **values,
        )
        db.add(existing)
    else:
        for key, value in values.items():
            setattr(existing, key, value)
    db.flush()
    return existing


def parse_args():
    parser = argparse.ArgumentParser(description="Backfill Yahoo SI=F history into readiness-compatible indicators.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Fetch and validate without writing rows.")
    mode.add_argument("--apply", action="store_true", help="Write backfilled rows.")
    parser.add_argument("--assets", default="XAG,XAG_GRAM", help="Comma-separated assets: XAG,XAG_GRAM")
    parser.add_argument("--timeframes", default="1d", help="Comma-separated timeframes; currently only 1d")
    parser.add_argument("--min-bars", type=int, default=60)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    backfill(
        dry_run=not args.apply,
        assets=[item.strip() for item in args.assets.split(",") if item.strip()],
        timeframes=[item.strip() for item in args.timeframes.split(",") if item.strip()],
        min_bars=args.min_bars,
    )
