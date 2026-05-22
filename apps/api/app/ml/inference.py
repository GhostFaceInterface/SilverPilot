import os
import pickle
import logging
from datetime import datetime, timedelta, UTC
from typing import Optional
import pandas as pd
import numpy as np
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import PriceSnapshot, RawFxRate, TechnicalIndicator, HistoricalAgentCache, AgentMemoryEvent

logger = logging.getLogger("silverpilot.ml.inference")

# Defensive import logic to prevent crashes if ML libraries are not available on VPS
try:
    import lightgbm  # noqa: F401

    LIGHTGBM_AVAILABLE = True
except ImportError:
    logger.warning(
        "LightGBM library is not installed in this environment. ML predictions will be disabled (graceful fallback)."
    )
    LIGHTGBM_AVAILABLE = False

# Global variables for model caching
_MODEL_CACHE = None
_MODEL_LOADED = False


def load_model() -> Optional[object]:
    """
    Loads and caches the champion LightGBM model in a thread-safe-like global check.
    Returns None if the library is missing, file is not found, or loading fails.
    """
    global _MODEL_CACHE, _MODEL_LOADED

    if _MODEL_LOADED:
        return _MODEL_CACHE

    if not LIGHTGBM_AVAILABLE:
        _MODEL_LOADED = True
        _MODEL_CACHE = None
        return None

    settings = get_settings()

    # Try finding the model file relative to root path or absolute path
    model_paths_to_try = [
        settings.risk_ml_model_path,
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), settings.risk_ml_model_path
        ),
        os.path.abspath(settings.risk_ml_model_path),
    ]

    resolved_path = None
    for p in model_paths_to_try:
        if os.path.exists(p):
            resolved_path = p
            break

    if not resolved_path:
        logger.warning(f"ML Model file not found at any expected path: {model_paths_to_try}. Disabling ML Veto.")
        _MODEL_LOADED = True
        _MODEL_CACHE = None
        return None

    try:
        logger.info(f"Loading champion model from {resolved_path}...")
        with open(resolved_path, "rb") as f:
            _MODEL_CACHE = pickle.load(f)
        _MODEL_LOADED = True
        logger.info("Successfully loaded champion ML model into memory.")
        return _MODEL_CACHE
    except Exception as e:
        logger.error(f"Error loading champion ML model: {e}. Fallback to None.")
        _MODEL_LOADED = True
        _MODEL_CACHE = None
        return None


def get_active_model_metadata() -> dict:
    """
    Reads the static champion_metadata.json file if available.
    Returns a dict with metadata, or a default dict if missing/uninitialized (fail-secure).
    """
    settings = get_settings()

    # Deriving metadata path based on model path
    model_path = settings.risk_ml_model_path
    metadata_path = model_path.replace("champion_model.pkl", "champion_metadata.json")
    if metadata_path == model_path:
        metadata_path = os.path.splitext(model_path)[0] + "_metadata.json"

    model_paths_to_try = [
        metadata_path,
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), metadata_path),
        os.path.abspath(metadata_path),
    ]

    resolved_path = None
    for p in model_paths_to_try:
        if os.path.exists(p):
            resolved_path = p
            break

    if not resolved_path:
        logger.warning(f"ML metadata file not found at any expected path: {model_paths_to_try}.")
        return {"model_status": "uninitialized"}

    try:
        import json

        with open(resolved_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.error(f"Error reading champion model metadata: {e}.")
        return {"model_status": "uninitialized"}


def extract_live_features(db: Session, asset_id: int) -> Optional[pd.DataFrame]:
    """
    Extracts the 11 ML features on-the-fly for the given asset from active database tables.
    Returns a 1-row Pandas DataFrame ready for prediction, or None if critical data is missing.
    Ensures absolute mathematical consistency with scripts/build_dataset.py.
    """
    try:
        # 1. Fetch the latest PriceSnapshot as anchor T
        stmt_latest_price = (
            select(PriceSnapshot)
            .where(PriceSnapshot.asset_id == asset_id)
            .order_by(desc(PriceSnapshot.observed_at))
            .limit(1)
        )
        latest_price = db.execute(stmt_latest_price).scalars().first()
        if not latest_price:
            logger.warning("No PriceSnapshots found in database. Cannot extract features.")
            return None

        anchor_time = latest_price.observed_at
        if anchor_time.tzinfo is None:
            anchor_time = anchor_time.replace(tzinfo=UTC)

        # 2. Fetch past prices to compute returns and volatility (need past 7 days)
        seven_days_ago = anchor_time - timedelta(days=7)
        stmt_past_prices = (
            select(PriceSnapshot)
            .where(PriceSnapshot.asset_id == asset_id)
            .where(PriceSnapshot.observed_at >= seven_days_ago)
            .where(PriceSnapshot.observed_at <= anchor_time)
            .order_by(PriceSnapshot.observed_at.asc())
        )
        past_prices = db.execute(stmt_past_prices).scalars().all()
        if len(past_prices) < 2:
            logger.warning("Insufficient historical price snapshots to compute returns.")
            return None

        # Convert to Pandas DataFrame for calculations
        df_price = pd.DataFrame(
            [
                {
                    "buy_price": float(p.buy_price),
                    "sell_price": float(p.sell_price),
                    "mid_price": float(p.mid_price),
                    "spread_percent": float(p.spread_percent) if p.spread_percent is not None else 0.0,
                    "observed_at": p.observed_at.replace(tzinfo=UTC)
                    if p.observed_at.tzinfo is None
                    else p.observed_at.astimezone(UTC),
                }
                for p in past_prices
            ]
        )

        # Current values (from anchor index)
        curr_idx = len(df_price) - 1
        curr_price_row = df_price.iloc[curr_idx]
        curr_mid = curr_price_row["mid_price"]

        # Feature A: bank_spread_percent
        # formula: spread_percent if not null/zero, else (buy - sell) / mid * 100
        spread_val = curr_price_row["spread_percent"]
        if spread_val is None or np.isclose(spread_val, 0.0):
            bank_spread_percent = ((curr_price_row["buy_price"] - curr_price_row["sell_price"]) / curr_mid) * 100.0
        else:
            bank_spread_percent = spread_val

        # Helper to get price closest to a target past time
        def get_past_mid_price(target_time: datetime, tolerance_hours: int) -> float:
            df_price["time_diff"] = (df_price["observed_at"] - target_time).abs()
            nearest_row = df_price.loc[df_price["time_diff"].idxmin()]
            if nearest_row["time_diff"] <= timedelta(hours=tolerance_hours):
                return nearest_row["mid_price"]
            return curr_mid  # Fallback to current if no data in tolerance

        # Feature B: xag_return_15m
        mid_15m = get_past_mid_price(anchor_time - timedelta(minutes=15), tolerance_hours=1)
        xag_return_15m = (curr_mid - mid_15m) / mid_15m if mid_15m > 0 else 0.0

        # Feature C: xag_return_1h
        mid_1h = get_past_mid_price(anchor_time - timedelta(hours=1), tolerance_hours=2)
        xag_return_1h = (curr_mid - mid_1h) / mid_1h if mid_1h > 0 else 0.0

        # Feature D: xag_return_24h
        mid_24h = get_past_mid_price(anchor_time - timedelta(hours=24), tolerance_hours=6)
        xag_return_24h = (curr_mid - mid_24h) / mid_24h if mid_24h > 0 else 0.0

        # Feature E: usd_try_return_24h
        # Fetch FX rate at T and T-24h
        stmt_latest_fx = (
            select(RawFxRate)
            .where(RawFxRate.source == "tcmb")
            .where(RawFxRate.observed_at <= anchor_time)
            .order_by(desc(RawFxRate.observed_at))
            .limit(1)
        )
        latest_fx = db.execute(stmt_latest_fx).scalars().first()

        stmt_past_fx = (
            select(RawFxRate)
            .where(RawFxRate.source == "tcmb")
            .where(RawFxRate.observed_at >= anchor_time - timedelta(hours=30))
            .where(RawFxRate.observed_at <= anchor_time - timedelta(hours=18))
            .order_by(desc(RawFxRate.observed_at))
            .limit(1)
        )
        past_fx = db.execute(stmt_past_fx).scalars().first()

        if latest_fx and past_fx:
            rate_curr = float(latest_fx.rate)
            rate_past = float(past_fx.rate)
            usd_try_return_24h = (rate_curr - rate_past) / rate_past if rate_past > 0 else 0.0
        else:
            usd_try_return_24h = 0.0

        # Feature F & G: Volatility (24h, 7d)
        # 1. Compute rolling 15m returns for the past prices
        df_price = df_price.sort_values("observed_at").reset_index(drop=True)
        # Shift matching structure to compute past returns (re-implementing pandas-ta/std returns)
        df_price["past_mid_15m"] = df_price["observed_at"].apply(
            lambda t: get_past_mid_price(t - timedelta(minutes=15), tolerance_hours=1)
        )
        df_price["ret_15m"] = (df_price["mid_price"] - df_price["past_mid_15m"]) / df_price["past_mid_15m"]
        df_price["ret_15m"] = df_price["ret_15m"].fillna(0.0)

        # 2. Set observed_at index for rolling std calculations
        df_price = df_price.set_index("observed_at", drop=False)
        vol_24h_series = df_price["ret_15m"].rolling("24h").std()
        vol_7d_series = df_price["ret_15m"].rolling("7D").std()

        volatility_24h = float(vol_24h_series.iloc[-1]) if not pd.isna(vol_24h_series.iloc[-1]) else 0.0
        volatility_7d = float(vol_7d_series.iloc[-1]) if not pd.isna(vol_7d_series.iloc[-1]) else 0.0

        # Feature H: xau_xag_ratio
        stmt_latest_ti = (
            select(TechnicalIndicator)
            .where(TechnicalIndicator.bar_timestamp <= anchor_time)
            .order_by(desc(TechnicalIndicator.bar_timestamp))
            .limit(1)
        )
        latest_ti = db.execute(stmt_latest_ti).scalars().first()
        xau_xag_ratio = float(latest_ti.xau_xag_ratio) if latest_ti and latest_ti.xau_xag_ratio else 80.0

        # Feature I: news_sentiment_score
        # Check AgentMemoryEvent first (highest priority)
        stmt_memory_sentiment = (
            select(AgentMemoryEvent)
            .where(AgentMemoryEvent.agent_name == "news-agent")
            .where(AgentMemoryEvent.event_type == "news_sentiment")
            .where(AgentMemoryEvent.created_at <= anchor_time)
            .order_by(desc(AgentMemoryEvent.created_at))
            .limit(1)
        )
        mem_sentiment = db.execute(stmt_memory_sentiment).scalars().first()

        sentiment_score = 0.0
        sentiment_val = None

        if mem_sentiment and mem_sentiment.value_json:
            sentiment_val = mem_sentiment.value_json.get("sentiment")
        else:
            # Fallback to HistoricalAgentCache
            stmt_cache_sentiment = (
                select(HistoricalAgentCache)
                .where(HistoricalAgentCache.agent_name == "news-agent")
                .where(HistoricalAgentCache.event_type == "news_sentiment")
                .where(HistoricalAgentCache.timestamp <= anchor_time)
                .order_by(desc(HistoricalAgentCache.timestamp))
                .limit(1)
            )
            cache_sentiment = db.execute(stmt_cache_sentiment).scalars().first()
            if cache_sentiment and cache_sentiment.value_json:
                sentiment_val = cache_sentiment.value_json.get("sentiment")

        if sentiment_val:
            sentiment_upper = str(sentiment_val).upper()
            if "BULLISH" in sentiment_upper:
                sentiment_score = 1.0
            elif "BEARISH" in sentiment_upper:
                sentiment_score = -1.0

        # Feature J & K: hour_of_day, day_of_week (UTC time)
        hour_of_day = float(anchor_time.hour)
        day_of_week = float(anchor_time.weekday())

        # Build feature dictionary
        feat_dict = {
            "bank_spread_percent": [bank_spread_percent],
            "xag_return_15m": [xag_return_15m],
            "xag_return_1h": [xag_return_1h],
            "xag_return_24h": [xag_return_24h],
            "usd_try_return_24h": [usd_try_return_24h],
            "volatility_24h": [volatility_24h],
            "volatility_7d": [volatility_7d],
            "xau_xag_ratio": [xau_xag_ratio],
            "news_sentiment_score": [sentiment_score],
            "hour_of_day": [hour_of_day],
            "day_of_week": [day_of_week],
        }

        df_feat = pd.DataFrame(feat_dict)
        return df_feat

    except Exception as e:
        logger.error(f"Failed to extract live features on-the-fly: {e}")
        return None


def predict_profitability(db: Session, asset_id: int) -> Optional[float]:
    """
    Predicts the profitability probability after costs for the 3-day horizon.
    Returns float probability [0.0, 1.0] if successful, or None on error / disabled state (bypass).
    """
    settings = get_settings()
    if not settings.risk_ml_model_enabled:
        return None

    # Load and cache model
    model = load_model()
    if model is None:
        return None

    # Extract live features
    df_feat = extract_live_features(db, asset_id)
    if df_feat is None:
        logger.warning("Live feature extraction failed. Bypassing ML prediction.")
        return None

    try:
        # Re-order features explicitly to match training FEATURES list
        FEATURES = [
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
        X = df_feat[FEATURES]

        # Predict probability of class 1 (profitable after costs)
        proba = model.predict_proba(X)[0, 1]
        logger.info(
            f"ML Predictor: Profitability Probability: {proba:.4f} (Threshold: {settings.risk_ml_min_probability})"
        )
        return float(proba)
    except Exception as e:
        logger.error(f"Error during model prediction step: {e}. Bypassing.")
        return None
