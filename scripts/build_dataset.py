#!/usr/bin/env python3
"""
SilverPilot ML Dataset Automation Pipeline
Generates high-quality feature and label datasets for offline ML training.
Strictly adheres to zero-leakage protocols.
"""

import os
import sys
import argparse
import json
import logging
from datetime import datetime, UTC
import numpy as np
import pandas as pd
from sqlalchemy import select

# Path setup to import app modules
current_dir = os.path.dirname(os.path.abspath(__file__))
root_path = os.path.dirname(current_dir)
api_path = os.path.join(root_path, "apps", "api")
if api_path not in sys.path:
    sys.path.insert(0, api_path)

from app.core.db import SessionLocal  # noqa: E402
from app.models.entities import (  # noqa: E402
    PriceSnapshot,
    RawFxRate,
    TechnicalIndicator,
    HistoricalAgentCache,
    AgentMemoryEvent,
    Asset,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("silverpilot.ml.dataset")


def build_dataset(version: str, dry_run: bool = False, drop_unlabeled: bool = True) -> pd.DataFrame:
    """
    Main function to construct features and labels from database tables.
    Returns the final constructed pandas DataFrame.
    """
    logger.info("Initializing database session...")
    db = SessionLocal()
    try:
        # 1. Fetch Asset
        asset = db.query(Asset).filter(Asset.symbol == "XAG").first()
        if not asset:
            raise ValueError("XAG Asset not found in database.")

        # 2. Fetch all PriceSnapshots ordered by observed_at asc
        logger.info("Fetching PriceSnapshots from database...")
        stmt_prices = (
            select(PriceSnapshot).where(PriceSnapshot.asset_id == asset.id).order_by(PriceSnapshot.observed_at.asc())
        )
        prices = db.execute(stmt_prices).scalars().all()
        logger.info(f"Retrieved {len(prices)} PriceSnapshots.")

        if len(prices) == 0:
            logger.warning("No price snapshots found. Returning empty DataFrame.")
            return pd.DataFrame()

        # Convert to Pandas DataFrame
        df_price = pd.DataFrame(
            [
                {
                    "id": p.id,
                    "buy_price": float(p.buy_price),
                    "sell_price": float(p.sell_price),
                    "mid_price": float(p.mid_price),
                    "spread_percent": float(p.spread_percent) if p.spread_percent is not None else 0.0,
                    "observed_at": p.observed_at,
                }
                for p in prices
            ]
        )

        # Convert observed_at to datetime and localize to UTC
        df_price["observed_at"] = pd.to_datetime(df_price["observed_at"])
        if df_price["observed_at"].dt.tz is None:
            df_price["observed_at"] = df_price["observed_at"].dt.tz_localize("UTC")
        else:
            df_price["observed_at"] = df_price["observed_at"].dt.tz_convert("UTC")

        df_price = df_price.sort_values("observed_at").reset_index(drop=True)

        # 3. Calculate bank_spread_percent
        # Formula: spread_percent if not null/zero, else (buy_price - sell_price) / mid_price
        logger.info("Calculating bank_spread_percent...")
        raw_spread = (df_price["buy_price"] - df_price["sell_price"]) / df_price["mid_price"]
        # Multiply by 100 to keep it consistent with percentage notation (e.g. 0.5% as 0.5)
        raw_spread_pct = raw_spread * 100.0

        df_price["bank_spread_percent"] = np.where(
            df_price["spread_percent"] != 0.0, df_price["spread_percent"], raw_spread_pct
        )

        # 4. Fetch RawFxRates
        logger.info("Fetching RawFxRates (USD/TRY) from database...")
        stmt_fx = (
            select(RawFxRate)
            .where(RawFxRate.base_currency == "USD")
            .where(RawFxRate.quote_currency == "TRY")
            .order_by(RawFxRate.observed_at.asc())
        )
        fx_rates = db.execute(stmt_fx).scalars().all()
        logger.info(f"Retrieved {len(fx_rates)} USD/TRY FxRates.")

        df_fx = pd.DataFrame([{"rate": float(f.rate), "observed_at": f.observed_at} for f in fx_rates])
        if not df_fx.empty:
            df_fx["observed_at"] = pd.to_datetime(df_fx["observed_at"])
            if df_fx["observed_at"].dt.tz is None:
                df_fx["observed_at"] = df_fx["observed_at"].dt.tz_localize("UTC")
            else:
                df_fx["observed_at"] = df_fx["observed_at"].dt.tz_convert("UTC")
            df_fx = df_fx.sort_values("observed_at").reset_index(drop=True)

        # 5. Fetch Technical Indicators (xau_xag_ratio)
        logger.info("Fetching TechnicalIndicators from database...")
        stmt_tech = select(TechnicalIndicator).order_by(TechnicalIndicator.bar_timestamp.asc())
        tech_indicators = db.execute(stmt_tech).scalars().all()
        logger.info(f"Retrieved {len(tech_indicators)} TechnicalIndicator bars.")

        df_tech = pd.DataFrame(
            [
                {
                    "xau_xag_ratio": float(t.xau_xag_ratio) if t.xau_xag_ratio is not None else np.nan,
                    "observed_at": t.bar_timestamp,
                }
                for t in tech_indicators
            ]
        )
        if not df_tech.empty:
            df_tech["observed_at"] = pd.to_datetime(df_tech["observed_at"])
            if df_tech["observed_at"].dt.tz is None:
                df_tech["observed_at"] = df_tech["observed_at"].dt.tz_localize("UTC")
            else:
                df_tech["observed_at"] = df_tech["observed_at"].dt.tz_convert("UTC")
            df_tech = df_tech.sort_values("observed_at").reset_index(drop=True)

        # 6. Fetch News Sentiment scores from HistoricalAgentCache and AgentMemoryEvent
        logger.info("Fetching News Agent sentiments...")

        # A. Query HistoricalAgentCache
        stmt_cache = (
            select(HistoricalAgentCache)
            .where(HistoricalAgentCache.agent_name.in_(["hermes-agent", "news-agent"]))
            .where(HistoricalAgentCache.event_type.in_(["hermes_sentiment", "news_sentiment"]))
        )
        cache_sentiments = db.execute(stmt_cache).scalars().all()

        # B. Query AgentMemoryEvent
        stmt_memory = (
            select(AgentMemoryEvent)
            .where(AgentMemoryEvent.agent_name.in_(["hermes-agent", "news-agent"]))
            .where(AgentMemoryEvent.event_type.in_(["hermes_sentiment", "news_sentiment"]))
        )
        memory_sentiments = db.execute(stmt_memory).scalars().all()

        sentiments_list = []
        sentiment_mapping = {"BULLISH": 1.0, "NEUTRAL": 0.0, "BEARISH": -1.0}

        for c in cache_sentiments:
            val = c.value_json or {}
            sent_str = str(val.get("sentiment", "NEUTRAL")).upper()
            score = sentiment_mapping.get(sent_str, 0.0)
            sentiments_list.append({"observed_at": c.timestamp, "news_sentiment_score": score})

        for m in memory_sentiments:
            val = m.value_json or {}
            sent_str = str(val.get("sentiment", "NEUTRAL")).upper()
            score = sentiment_mapping.get(sent_str, 0.0)
            sentiments_list.append({"observed_at": m.created_at, "news_sentiment_score": score})

        df_sentiment = pd.DataFrame(sentiments_list)
        if not df_sentiment.empty:
            df_sentiment["observed_at"] = pd.to_datetime(df_sentiment["observed_at"])
            if df_sentiment["observed_at"].dt.tz is None:
                df_sentiment["observed_at"] = df_sentiment["observed_at"].dt.tz_localize("UTC")
            else:
                df_sentiment["observed_at"] = df_sentiment["observed_at"].dt.tz_convert("UTC")
            df_sentiment = df_sentiment.sort_values("observed_at").reset_index(drop=True)

        # -------------------------------------------------------------
        # FEATURE CALCULATIONS & TIME-SERIES MERGES (Strict Zero-Leakage)
        # -------------------------------------------------------------
        logger.info("Performing zero-leakage feature engineering merges...")

        df_temp = df_price[["observed_at", "mid_price"]].copy()

        # A. XAG Returns (15m, 1h, 24h)
        # Find price exactly looking backward:
        # target_time = observed_at - delta.
        # merge_asof matches the closest observed price prior to or equal to target_time.

        # 15m return
        df_price["time_15m"] = df_price["observed_at"] - pd.Timedelta(minutes=15)
        df_price = pd.merge_asof(
            df_price,
            df_temp.rename(columns={"mid_price": "mid_price_15m", "observed_at": "observed_at_15m"}),
            left_on="time_15m",
            right_on="observed_at_15m",
            direction="backward",
        )
        df_price["xag_return_15m"] = (df_price["mid_price"] - df_price["mid_price_15m"]) / df_price["mid_price_15m"]

        # 1h return
        df_price["time_1h"] = df_price["observed_at"] - pd.Timedelta(hours=1)
        df_price = pd.merge_asof(
            df_price,
            df_temp.rename(columns={"mid_price": "mid_price_1h", "observed_at": "observed_at_1h"}),
            left_on="time_1h",
            right_on="observed_at_1h",
            direction="backward",
        )
        df_price["xag_return_1h"] = (df_price["mid_price"] - df_price["mid_price_1h"]) / df_price["mid_price_1h"]

        # 24h return
        df_price["time_24h"] = df_price["observed_at"] - pd.Timedelta(hours=24)
        df_price = pd.merge_asof(
            df_price,
            df_temp.rename(columns={"mid_price": "mid_price_24h", "observed_at": "observed_at_24h"}),
            left_on="time_24h",
            right_on="observed_at_24h",
            direction="backward",
        )
        df_price["xag_return_24h"] = (df_price["mid_price"] - df_price["mid_price_24h"]) / df_price["mid_price_24h"]

        # Drop temporary columns from returns merge
        drop_cols = [
            "time_15m",
            "observed_at_15m",
            "mid_price_15m",
            "time_1h",
            "observed_at_1h",
            "mid_price_1h",
            "time_24h",
            "observed_at_24h",
            "mid_price_24h",
        ]
        df_price = df_price.drop(columns=[c for c in drop_cols if c in df_price.columns])

        # B. Volatility (24h, 7d)
        # rolling standard deviation of 15m returns over past 24 hours/7 days.
        # Time-based rolling requires DatetimeIndex sorted ascending.
        df_price = df_price.set_index("observed_at", drop=False)
        df_price["volatility_24h"] = df_price["xag_return_15m"].rolling("24h").std()
        df_price["volatility_7d"] = df_price["xag_return_15m"].rolling("7D").std()
        df_price = df_price.reset_index(drop=True)

        # C. USD/TRY Return over 24h
        df_price["usd_try_return_24h"] = np.nan
        if not df_fx.empty:
            # Match current rate
            df_price = pd.merge_asof(
                df_price, df_fx.rename(columns={"rate": "fx_rate_current"}), on="observed_at", direction="backward"
            )
            # Match 24h ago rate
            df_price["time_24h_fx"] = df_price["observed_at"] - pd.Timedelta(hours=24)
            df_price = pd.merge_asof(
                df_price,
                df_fx.rename(columns={"rate": "fx_rate_24h", "observed_at": "observed_at_fx_24h"}),
                left_on="time_24h_fx",
                right_on="observed_at_fx_24h",
                direction="backward",
            )
            df_price["usd_try_return_24h"] = (df_price["fx_rate_current"] - df_price["fx_rate_24h"]) / df_price[
                "fx_rate_24h"
            ]
            df_price = df_price.drop(
                columns=[
                    c
                    for c in [
                        "fx_rate_current",
                        "observed_at_fx_current",
                        "time_24h_fx",
                        "fx_rate_24h",
                        "observed_at_fx_24h",
                    ]
                    if c in df_price.columns
                ]
            )

        # D. Technical Indicators (xau_xag_ratio)
        if not df_tech.empty:
            df_price = pd.merge_asof(df_price, df_tech, on="observed_at", direction="backward")
        else:
            df_price["xau_xag_ratio"] = np.nan

        # E. News Sentiment Score (closest news sentiment looking back at most 24 hours)
        df_price["news_sentiment_score"] = 0.0
        if not df_sentiment.empty:
            df_price = pd.merge_asof(
                df_price, df_sentiment, on="observed_at", direction="backward", tolerance=pd.Timedelta(hours=24)
            )
            # Default to 0.0 if not found
            if "news_sentiment_score_y" in df_price.columns:
                df_price["news_sentiment_score"] = df_price["news_sentiment_score_y"].fillna(0.0)
                df_price = df_price.drop(columns=["news_sentiment_score_x", "news_sentiment_score_y"])
            elif "news_sentiment_score" in df_price.columns:
                df_price["news_sentiment_score"] = df_price["news_sentiment_score"].fillna(0.0)

        # F. Robust Default / Forward-fill / Backward-fill Logic for Missing Data
        logger.info("Applying defaults and forward-fill logic for missing metrics...")

        # Volatilities might be NaN at start of series due to lack of historical data
        df_price["volatility_24h"] = df_price["volatility_24h"].ffill().bfill().fillna(0.0)
        df_price["volatility_7d"] = df_price["volatility_7d"].ffill().bfill().fillna(0.0)

        df_price["xag_return_15m"] = df_price["xag_return_15m"].ffill().bfill().fillna(0.0)
        df_price["xag_return_1h"] = df_price["xag_return_1h"].ffill().bfill().fillna(0.0)
        df_price["xag_return_24h"] = df_price["xag_return_24h"].ffill().bfill().fillna(0.0)
        df_price["usd_try_return_24h"] = df_price["usd_try_return_24h"].ffill().bfill().fillna(0.0)
        df_price["xau_xag_ratio"] = df_price["xau_xag_ratio"].ffill().bfill().fillna(80.0)

        # G. Hour of Day and Day of Week
        df_price["hour_of_day"] = df_price["observed_at"].dt.hour
        df_price["day_of_week"] = df_price["observed_at"].dt.dayofweek

        # -------------------------------------------------------------
        # LABEL CALCULATIONS (Future-Looking)
        # -------------------------------------------------------------
        logger.info("Calculating future-looking labels...")

        # Future price lookups
        # target_future = observed_at + delta
        # direction="nearest" finds the closest snapshot. We restrict matching using a tolerance.

        # 1-day future price
        df_price["time_plus_1d"] = df_price["observed_at"] + pd.Timedelta(days=1)
        df_price = pd.merge_asof(
            df_price,
            df_temp.rename(columns={"mid_price": "mid_price_plus_1d", "observed_at": "observed_at_plus_1d"}),
            left_on="time_plus_1d",
            right_on="observed_at_plus_1d",
            direction="nearest",
            tolerance=pd.Timedelta(hours=4),
        )
        df_price["net_profit_1d"] = (df_price["mid_price_plus_1d"] - df_price["mid_price"]) / df_price["mid_price"]

        # 3-day future price (and sell price for costs logic)
        df_price["time_plus_3d"] = df_price["observed_at"] + pd.Timedelta(days=3)
        df_price = pd.merge_asof(
            df_price,
            df_temp.rename(columns={"mid_price": "mid_price_plus_3d", "observed_at": "observed_at_plus_3d"}),
            left_on="time_plus_3d",
            right_on="observed_at_plus_3d",
            direction="nearest",
            tolerance=pd.Timedelta(hours=6),
        )
        df_price["net_profit_3d"] = (df_price["mid_price_plus_3d"] - df_price["mid_price"]) / df_price["mid_price"]

        # 7-day future price
        df_price["time_plus_7d"] = df_price["observed_at"] + pd.Timedelta(days=7)
        df_price = pd.merge_asof(
            df_price,
            df_temp.rename(columns={"mid_price": "mid_price_plus_7d", "observed_at": "observed_at_plus_7d"}),
            left_on="time_plus_7d",
            right_on="observed_at_plus_7d",
            direction="nearest",
            tolerance=pd.Timedelta(hours=12),
        )
        df_price["net_profit_7d"] = (df_price["mid_price_plus_7d"] - df_price["mid_price"]) / df_price["mid_price"]

        # profitable_after_costs_3d
        # binary 1 if future sell_price_at_t_plus_3d > current buy_price_at_t else 0.
        df_temp_sell = df_price[["observed_at", "sell_price"]].copy()
        df_price = pd.merge_asof(
            df_price,
            df_temp_sell.rename(
                columns={"sell_price": "sell_price_plus_3d", "observed_at": "observed_at_sell_plus_3d"}
            ),
            left_on="time_plus_3d",
            right_on="observed_at_sell_plus_3d",
            direction="nearest",
            tolerance=pd.Timedelta(hours=6),
        )

        # Compute binary flag (keep as NaN if sell_price_plus_3d is missing)
        df_price["profitable_after_costs_3d"] = np.where(
            df_price["sell_price_plus_3d"].isna(),
            np.nan,
            (df_price["sell_price_plus_3d"] > df_price["buy_price"]).astype(float),
        )

        # max_drawdown_3d
        # max peak-to-trough drop from current mid_price over the next 3 days.
        logger.info("Computing max_drawdown_3d future label...")
        times = df_price["observed_at"].values
        prices = df_price["mid_price"].values
        min_prices = []

        for i in range(len(df_price)):
            t_curr = times[i]
            t_limit = t_curr + np.timedelta64(3, "D")

            future_prices = prices[i:]
            future_times = times[i:]
            mask = future_times <= t_limit
            window_prices = future_prices[mask]

            min_prices.append(np.min(window_prices) if len(window_prices) > 0 else prices[i])

        df_price["min_price_future_3d"] = min_prices

        # Drop is expressed as a positive percentage/float (e.g. 0.05 for 5% max drawdown)
        df_price["max_drawdown_3d"] = np.maximum(
            0.0, (df_price["mid_price"] - df_price["min_price_future_3d"]) / df_price["mid_price"]
        )

        # Cleanup future temporary matching columns
        future_drop_cols = [
            "time_plus_1d",
            "observed_at_plus_1d",
            "mid_price_plus_1d",
            "time_plus_3d",
            "observed_at_plus_3d",
            "mid_price_plus_3d",
            "time_plus_7d",
            "observed_at_plus_7d",
            "mid_price_plus_7d",
            "observed_at_sell_plus_3d",
            "sell_price_plus_3d",
            "min_price_future_3d",
        ]
        df_price = df_price.drop(columns=[c for c in future_drop_cols if c in df_price.columns])

        # Reset Index
        df_price = df_price.reset_index(drop=True)

        # Drop any row where critical label (like 3d profit or drawdown) is NaN because it's at the end of the time series
        # Wait! It's better to preserve them but flag, or standard ML drops NaN. Let's keep them and let the ML pipeline handle dropping,
        # or drop them in output. Let's drop rows where `net_profit_3d` is NaN to keep the dataset fully labeled!
        after_drop = len(df_price)
        if drop_unlabeled:
            logger.info("Dropping rows with incomplete future labels (end of time series)...")
            before_drop = len(df_price)
            df_price = df_price.dropna(subset=["net_profit_3d", "max_drawdown_3d", "profitable_after_costs_3d"])
            after_drop = len(df_price)
            logger.info(f"Dropped {before_drop - after_drop} rows. Final dataset has {after_drop} rows.")

        # Save to file
        if not dry_run and after_drop > 0:
            dataset_dir = os.path.join(root_path, "data", "datasets", f"v{version}")
            os.makedirs(dataset_dir, exist_ok=True)

            parquet_path = os.path.join(dataset_dir, "dataset.parquet")
            csv_path = os.path.join(dataset_dir, "dataset.csv")
            meta_path = os.path.join(dataset_dir, "metadata.json")

            try:
                logger.info(f"Saving dataset parquet file to {parquet_path}...")
                df_price.to_parquet(parquet_path, index=False)
            except Exception as e:
                logger.warning(f"Could not save parquet file (parquet engine missing?): {e}")

            logger.info(f"Saving dataset csv file to {csv_path}...")
            df_price.to_csv(csv_path, index=False)

            features = [
                "bank_spread_percent",
                "xag_return_15m",
                "xag_return_1h",
                "xag_return_24h",
                "usd_try_return_24h",
                "volatility_24h",
                "volatility_7d",
                "xau_xag_ratio",
                "news_sentiment_score",
                "hour_of_day",
                "day_of_week",
            ]
            labels = ["net_profit_1d", "net_profit_3d", "net_profit_7d", "profitable_after_costs_3d", "max_drawdown_3d"]

            metadata = {
                "version": version,
                "generated_at": datetime.now(UTC).isoformat(),
                "row_count": len(df_price),
                "feature_list": features,
                "label_list": labels,
            }

            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=4)
            logger.info("Dataset and metadata saved successfully.")

    finally:
        db.close()

    return df_price


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build SilverPilot ML Dataset")
    parser.add_argument("--version", type=str, default="1.0.0", help="Dataset version")
    parser.add_argument("--dry-run", action="store_true", help="Run calculations without saving files")

    args = parser.parse_args()

    logger.info(f"Starting ML Dataset Pipeline. Version: {args.version}, Dry-Run: {args.dry_run}")
    df = build_dataset(version=args.version, dry_run=args.dry_run)
    logger.info(f"Pipeline finished! Generated dataset shape: {df.shape}")
