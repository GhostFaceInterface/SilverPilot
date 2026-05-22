#!/usr/bin/env python3
"""
SilverPilot Training Data Seeder
Populates local database (SQLite/PostgreSQL) with rich mock time-series data
to support offline model training pipelines in CI environments.
"""

import os
import sys
from datetime import datetime, UTC, timedelta
from decimal import Decimal

# Path setup to import app modules
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
api_path = os.path.join(root_path, "apps", "api")
if api_path not in sys.path:
    sys.path.insert(0, api_path)

from app.core.db import SessionLocal
from app.models.entities import (
    Asset, PriceSnapshot, RawFxRate, TechnicalIndicator,
    HistoricalAgentCache, CollectorRun
)

def seed_data():
    db = SessionLocal()
    try:
        # Pre-seed basic Asset
        asset = db.query(Asset).filter(Asset.symbol == "XAG").first()
        if not asset:
            asset = Asset(symbol="XAG", name="Silver", asset_type="metal", is_active=True)
            db.add(asset)
            db.flush()
        
        # Add CollectorRun
        start_time = datetime.now(UTC) - timedelta(days=20)
        run = db.query(CollectorRun).filter(CollectorRun.collector_name == "tcmb_usd_try").first()
        if not run:
            run = CollectorRun(
                collector_name="tcmb_usd_try",
                source="tcmb-today-xml",
                status="success",
                records_seen=1,
                records_inserted=1,
                started_at=start_time,
                finished_at=start_time,
                details_json={}
            )
            db.add(run)
            db.flush()
        
        # Add RawFxRate
        fx = db.query(RawFxRate).filter(RawFxRate.base_currency == "USD").first()
        if not fx:
            fx = RawFxRate(
                collector_run_id=run.id,
                source="tcmb-today-xml",
                base_currency="USD",
                quote_currency="TRY",
                rate=Decimal("32.500000"),
                observed_at=start_time,
                fetched_at=start_time,
                raw_payload_hash="dummy",
                parser_version="1.0.0",
                payload_json={}
            )
            db.add(fx)
            db.flush()

        print("Seeding PriceSnapshots and TechnicalIndicators...")
        count = 500
        for i in range(count):
            t = start_time + timedelta(minutes=i * 15)
            mid = 25.0 + (i * 0.02)  # steadily rising price
            if i > 250:
                mid = 30.0 - ((i - 250) * 0.01)

            buy_price = mid * 1.005
            sell_price = mid * 0.995
            
            p = PriceSnapshot(
                asset_id=asset.id,
                source="kuveyt_public_silver",
                buy_price=Decimal(str(buy_price)),
                sell_price=Decimal(str(sell_price)),
                mid_price=Decimal(str(mid)),
                currency="TRY",
                spread_absolute=Decimal(str(buy_price - sell_price)),
                spread_percent=Decimal("1.0"),
                observed_at=t
            )
            db.add(p)
            db.flush()

            # Technical indicators
            ind = TechnicalIndicator(
                price_snapshot_id=p.id,
                bar_timestamp=t,
                timeframe="15m",
                close_usd_oz=Decimal(str(mid)),
                rsi_14=Decimal("45.0") if i < 200 else Decimal("75.0"),
                macd_line=Decimal("0.5"),
                macd_signal=Decimal("0.4"),
                macd_histogram=Decimal("0.1"),
                bb_upper_20_2=Decimal(str(mid * 1.02)),
                bb_middle_20_2=Decimal(str(mid)),
                bb_lower_20_2=Decimal(str(mid * 0.98)),
                sma_20=Decimal(str(mid)),
                sma_50=Decimal(str(mid)),
                sma_200=Decimal(str(mid)),
                atr_14=Decimal("0.5"),
                xau_xag_ratio=Decimal("80.0")
            )
            db.add(ind)
            
            # Add Agent Veto records occasionally
            if i % 10 == 0:
                db.add(HistoricalAgentCache(
                    agent_name="news-agent",
                    event_type="news_sentiment",
                    timestamp=t,
                    value_json={
                        "decision": "BULLISH" if i % 20 == 0 else "BEARISH",
                        "reason": "Mock sentiment",
                        "confidence": 0.85
                    }
                ))

        db.commit()
        print(f"Successfully seeded database with {count} price indices.")
    except Exception as e:
        db.rollback()
        print(f"Seeding failed: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
