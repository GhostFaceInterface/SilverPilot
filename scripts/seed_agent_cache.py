import os
import sys
from datetime import datetime, UTC
from decimal import Decimal

# Path setup to import app modules from apps/api
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
api_path = os.path.join(root_path, "apps", "api")
if api_path not in sys.path:
    sys.path.insert(0, api_path)

from app.core.db import SessionLocal
from app.models import Asset, PriceSnapshot, TechnicalIndicator

def seed_cache():
    db = SessionLocal()
    try:
        # Check if HistoricalAgentCache model is defined in app.models
        try:
            from app.models import HistoricalAgentCache
        except ImportError:
            print("\033[1;31m[ERROR] HistoricalAgentCache is not defined in app.models.\033[0m")
            print("Please ensure Phase 1 is completed by the backend-architect before running the seeder.")
            sys.exit(1)

        if HistoricalAgentCache is None:
            print("\033[1;31m[ERROR] HistoricalAgentCache model is None. Please check if it was imported correctly.\033[0m")
            sys.exit(1)

        print("\033[1;34m[INFO] Fetching Asset XAG...\033[0m")
        asset = db.query(Asset).filter(Asset.symbol == "XAG").first()
        if not asset:
            print("\033[1;31m[ERROR] Asset XAG (Silver Spot) not found in database!\033[0m")
            sys.exit(1)

        # Clear existing cache entries to prevent duplicates
        print("\033[1;34m[INFO] Deleting old historical cache entries...\033[0m")
        deleted_count = db.query(HistoricalAgentCache).delete()
        print(f"\033[1;32m[SUCCESS] Deleted {deleted_count} old cache entries.\033[0m")

        timeframes = ["1d", "5m"]
        total_seeded = 0

        for timeframe in timeframes:
            print(f"\033[1;34m[INFO] Querying price snapshots for timeframe '{timeframe}'...\033[0m")
            
            # Fetch PriceSnapshots that have a TechnicalIndicator record for this timeframe
            records = (
                db.query(PriceSnapshot)
                .join(TechnicalIndicator, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
                .filter(PriceSnapshot.asset_id == asset.id)
                .filter(TechnicalIndicator.timeframe == timeframe)
                .order_by(PriceSnapshot.observed_at.asc())
                .all()
            )

            total_records = len(records)
            print(f"[INFO] Found {total_records} records for timeframe '{timeframe}'.")

            if total_records == 0:
                continue

            previous_mid_price = None
            cache_entries = []

            for bar in records:
                observed_at = bar.observed_at
                mid_price = bar.mid_price

                # Determine sentiment based on mid_price change
                if previous_mid_price is None:
                    sentiment = "NEUTRAL"
                    confidence = 0.60
                elif mid_price > previous_mid_price:
                    sentiment = "BULLISH"
                    confidence = 0.85
                elif mid_price < previous_mid_price:
                    sentiment = "BEARISH"
                    confidence = 0.85
                else:
                    sentiment = "NEUTRAL"
                    confidence = 0.60

                previous_mid_price = mid_price

                # News Agent Entry
                news_val = {
                    "sentiment": sentiment,
                    "confidence": confidence,
                    "summary_markdown": f"Historical mock sentiment for price bar on {observed_at}"
                }
                news_entry = HistoricalAgentCache(
                    agent_name="news-agent",
                    event_type="news_sentiment",
                    timestamp=observed_at,
                    value_json=news_val
                )
                cache_entries.append(news_entry)

                # Risk Agent Entry
                if sentiment == "BULLISH":
                    decision = "APPROVED"
                    risk_conf = 0.90
                elif sentiment == "BEARISH":
                    decision = "REJECTED"
                    risk_conf = 0.90
                else:
                    decision = "APPROVED"
                    risk_conf = 0.70

                risk_val = {
                    "decision": decision,
                    "confidence": risk_conf,
                    "critique_markdown": f"Historical mock critique for price bar on {observed_at}"
                }
                risk_entry = HistoricalAgentCache(
                    agent_name="risk-agent",
                    event_type="signal_critique",
                    timestamp=observed_at,
                    value_json=risk_val
                )
                cache_entries.append(risk_entry)

            # Bulk insert for efficiency
            if cache_entries:
                db.add_all(cache_entries)
                db.commit()
                total_seeded += len(cache_entries)
                print(f"\033[1;32m[SUCCESS] Seeded {len(cache_entries)} entries ({total_records} bars) for timeframe '{timeframe}'.\033[0m")

        print(f"\n\033[1;32m[COMPLETE] Successfully seeded a total of {total_seeded} cache entries!\033[0m")

    except Exception as exc:
        db.rollback()
        print(f"\033[1;31m[ERROR] Seeding failed: {exc}\033[0m", file=sys.stderr)
        raise exc
    finally:
        db.close()

if __name__ == "__main__":
    seed_cache()
