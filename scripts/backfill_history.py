import os
import sys
import json
import httpx
from datetime import UTC, datetime
from decimal import Decimal
import pandas as pd

# Path setup to import app modules
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
api_path = os.path.join(root_path, "apps", "api")
if api_path not in sys.path:
    sys.path.insert(0, api_path)

from app.core.db import SessionLocal
from app.models import Asset, CollectorRun, PriceSnapshot, RawGlobalPrice, TechnicalIndicator
from app.services.indicators import calculate_indicators

def backfill():
    db = SessionLocal()
    try:
        # 1. Fetch Asset
        asset = db.query(Asset).filter(Asset.symbol == "XAG").first()
        if not asset:
            print("XAG Asset not found. Creating it...")
            asset = Asset(symbol="XAG", name="Silver Spot", asset_type="metal", is_active=True)
            db.add(asset)
            db.commit()
            db.refresh(asset)

        print(f"XAG Asset ID: {asset.id}")

        # 2. Start Collector Run
        run = CollectorRun(
            collector_name="yahoo_xag_usd_backfill",
            source="yahoo-si-f-1d",
            status="running",
            records_seen=0,
            records_inserted=0,
            duplicates=0,
            details_json={"asset_symbol": "XAG"},
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        # 3. Fetch 2 years of daily data from Yahoo Finance
        url = "https://query1.finance.yahoo.com/v8/finance/chart/SI=F"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json"
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
        
        # Build DataFrame
        records = []
        for i in range(len(timestamps)):
            t = timestamps[i]
            c = closes[i]
            if t is None or c is None:
                continue
            o = opens[i] if i < len(opens) and opens[i] is not None else c
            h = highs[i] if i < len(highs) and highs[i] is not None else c
            l = lows[i] if i < len(lows) and lows[i] is not None else c
            v = volumes[i] if i < len(volumes) and volumes[i] is not None else 0.0
            
            records.append({
                "timestamp": int(t),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
            })
            
        df = pd.DataFrame(records)
        df = df.sort_values("timestamp").reset_index(drop=True)
        print(f"Loaded {len(df)} price bars from Yahoo Finance. Calculating indicators...")
        
        # Calculate technical indicators
        df_indicators = calculate_indicators(df)
        
        # Insert records
        seen = 0
        inserted = 0
        duplicates = 0
        
        for idx, row in df_indicators.iterrows():
            seen += 1
            observed_at = datetime.fromtimestamp(int(row["timestamp"]), tz=UTC)
            
            # Check for existing snapshot
            existing_snap = db.query(PriceSnapshot).filter(
                PriceSnapshot.asset_id == asset.id,
                PriceSnapshot.source == "yahoo-si-f-1d",
                PriceSnapshot.observed_at == observed_at
            ).first()
            
            if existing_snap:
                duplicates += 1
                continue
                
            close_price = Decimal(str(row["close"]))
            
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
            
            # Create RawGlobalPrice
            raw_global = RawGlobalPrice(
                collector_run_id=run.id,
                asset_id=asset.id,
                source="yahoo-si-f-1d",
                buy_price=close_price,
                sell_price=close_price,
                currency="USD",
                observed_at=observed_at,
                fetched_at=datetime.now(UTC),
                raw_payload_hash="backfill_" + str(row["timestamp"]),
                parser_version="yahoo-finance-chart-v1",
                payload_json=payload_dict,
            )
            db.add(raw_global)
            db.flush()
            
            # Create PriceSnapshot
            snap = PriceSnapshot(
                asset_id=asset.id,
                source="yahoo-si-f-1d",
                buy_price=close_price,
                sell_price=close_price,
                mid_price=close_price,
                currency="USD",
                spread_absolute=Decimal("0.0"),
                spread_percent=Decimal("0.0"),
                observed_at=observed_at,
                resolved_source="yahoo_si_f",
                is_degraded=False,
            )
            db.add(snap)
            db.flush()
            
            # Helper to convert float to Decimal safely
            def to_dec(val):
                if pd.isna(val) or val is None:
                    return None
                return Decimal(str(val))
                
            # Create TechnicalIndicator
            ti = TechnicalIndicator(
                price_snapshot_id=snap.id,
                bar_timestamp=observed_at,
                timeframe="1d",
                close_usd_oz=close_price,
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
            db.add(ti)
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
        print(f"\nBackfill completed successfully!")
        print(f"Total processed: {seen}")
        print(f"Total inserted: {inserted}")
        print(f"Total duplicates skipped: {duplicates}")
        
    except Exception as exc:
        db.rollback()
        print(f"Backfill failed: {exc}", file=sys.stderr)
        raise exc
    finally:
        db.close()

if __name__ == "__main__":
    backfill()
