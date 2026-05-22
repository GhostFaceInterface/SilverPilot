import logging
import pandas as pd
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import TechnicalIndicator, PriceSnapshot

logger = logging.getLogger("silverpilot.services.regime")

def get_market_regime(db: Session, limit: int = 50) -> dict:
    """
    Computes the market regime (TRENDING_UP, TRENDING_DOWN, SIDEWAYS) using ADX, 
    Bollinger Bandwidth, and SMA values.
    
    Robustness features:
    - Handles database cold starts (less than 14 records).
    - Fills or calculates missing indicators dynamically.
    - Handles NaN or infinity cleanly.
    """
    try:
        # Fetch latest TechnicalIndicator records
        stmt = (
            select(TechnicalIndicator)
            .join(PriceSnapshot, TechnicalIndicator.price_snapshot_id == PriceSnapshot.id)
            .order_by(TechnicalIndicator.bar_timestamp.desc())
            .limit(limit)
        )
        results = db.execute(stmt).scalars().all()
        
        # If there are fewer than 14 records, return SIDEWAYS safely
        if len(results) < 14:
            logger.info(f"Insufficient indicator data (found {len(results)}). Defaulting to SIDEWAYS.")
            return {
                "regime": "SIDEWAYS",
                "adx": 0.0,
                "bb_bandwidth": 0.0,
                "relative_atr": 0.0,
            }
            
        # Reverse to chronological order (oldest first)
        results.reverse()
        
        # Build list of records
        data = []
        for ind in results:
            snapshot = ind.price_snapshot
            if not snapshot:
                continue
            
            buy_p = float(snapshot.buy_price) if snapshot.buy_price is not None else float(ind.close_usd_oz or 0.0)
            sell_p = float(snapshot.sell_price) if snapshot.sell_price is not None else float(ind.close_usd_oz or 0.0)
            close_p = float(ind.close_usd_oz) if ind.close_usd_oz is not None else float(snapshot.mid_price or 0.0)
            
            data.append({
                "timestamp": ind.bar_timestamp,
                "high": buy_p,
                "low": sell_p,
                "close": close_p,
                "bb_upper": float(ind.bb_upper_20_2) if ind.bb_upper_20_2 is not None else np.nan,
                "bb_middle": float(ind.bb_middle_20_2) if ind.bb_middle_20_2 is not None else np.nan,
                "bb_lower": float(ind.bb_lower_20_2) if ind.bb_lower_20_2 is not None else np.nan,
                "sma_20": float(ind.sma_20) if ind.sma_20 is not None else np.nan,
                "sma_50": float(ind.sma_50) if ind.sma_50 is not None else np.nan,
                "atr_14": float(ind.atr_14) if ind.atr_14 is not None else np.nan,
            })
            
        df = pd.DataFrame(data)
        if len(df) < 14:
            return {
                "regime": "SIDEWAYS",
                "adx": 0.0,
                "bb_bandwidth": 0.0,
                "relative_atr": 0.0,
            }
            
        # Ensure values are clean
        df['close_prev'] = df['close'].shift(1)
        df['high_prev'] = df['high'].shift(1)
        df['low_prev'] = df['low'].shift(1)
        
        # Calculate TR (True Range)
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close_prev']).abs()
        tr3 = (df['low'] - df['close_prev']).abs()
        df['TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Calculate +DM and -DM
        df['plus_DM'] = np.where(
            (df['high'] - df['high_prev'] > df['low_prev'] - df['low']) & (df['high'] - df['high_prev'] > 0),
            df['high'] - df['high_prev'],
            0.0
        )
        df['minus_DM'] = np.where(
            (df['low_prev'] - df['low'] > df['high'] - df['high_prev']) & (df['low_prev'] - df['low'] > 0),
            df['low_prev'] - df['low'],
            0.0
        )
        
        # Wilder's Smoothing (alpha = 1/14)
        df['TR_smoothed'] = df['TR'].ewm(alpha=1.0/14.0, min_periods=14, adjust=False).mean()
        df['plus_DM_smoothed'] = df['plus_DM'].ewm(alpha=1.0/14.0, min_periods=14, adjust=False).mean()
        df['minus_DM_smoothed'] = df['minus_DM'].ewm(alpha=1.0/14.0, min_periods=14, adjust=False).mean()
        
        # Compute +DI and -DI
        df['plus_DI'] = 100.0 * (df['plus_DM_smoothed'] / df['TR_smoothed'].replace(0, np.nan))
        df['minus_DI'] = 100.0 * (df['minus_DM_smoothed'] / df['TR_smoothed'].replace(0, np.nan))
        df['plus_DI'] = df['plus_DI'].fillna(0.0)
        df['minus_DI'] = df['minus_DI'].fillna(0.0)
        
        # DX
        diff_di = (df['plus_DI'] - df['minus_DI']).abs()
        sum_di = df['plus_DI'] + df['minus_DI']
        df['DX'] = 100.0 * (diff_di / sum_di.replace(0, np.nan))
        df['DX'] = df['DX'].fillna(0.0)
        
        # ADX = EMA(DX, 14)
        df['ADX'] = df['DX'].ewm(alpha=1.0/14.0, min_periods=14, adjust=False).mean()
        df['ADX'] = df['ADX'].fillna(0.0)
        
        # Extract latest values
        latest_row = df.iloc[-1]
        close_price = latest_row['close']
        bb_upper = latest_row['bb_upper']
        bb_middle = latest_row['bb_middle']
        bb_lower = latest_row['bb_lower']
        sma_20 = latest_row['sma_20']
        sma_50 = latest_row['sma_50']
        atr_14 = latest_row['atr_14']
        adx = float(latest_row['ADX'])
        
        # Fallbacks for missing Bollinger/SMA values
        if pd.isna(bb_middle) or bb_middle == 0:
            sma_roll = df['close'].rolling(20).mean()
            std_roll = df['close'].rolling(20).std()
            bb_middle = float(sma_roll.iloc[-1]) if not pd.isna(sma_roll.iloc[-1]) else close_price
            bb_upper = float((sma_roll + 2 * std_roll).iloc[-1]) if not pd.isna(std_roll.iloc[-1]) else close_price
            bb_lower = float((sma_roll - 2 * std_roll).iloc[-1]) if not pd.isna(std_roll.iloc[-1]) else close_price
        else:
            bb_middle = float(bb_middle)
            bb_upper = float(bb_upper)
            bb_lower = float(bb_lower)
            
        if pd.isna(sma_20):
            sma_20_val = df['close'].rolling(20).mean().iloc[-1]
            sma_20 = float(sma_20_val) if not pd.isna(sma_20_val) else close_price
        else:
            sma_20 = float(sma_20)
            
        if pd.isna(sma_50):
            sma_50_val = df['close'].rolling(50).mean().iloc[-1]
            sma_50 = float(sma_50_val) if not pd.isna(sma_50_val) else close_price
        else:
            sma_50 = float(sma_50)
            
        if pd.isna(atr_14):
            df['atr_calc'] = df['TR'].ewm(alpha=1.0/14.0, min_periods=14, adjust=False).mean()
            atr_14 = float(df['atr_calc'].iloc[-1]) if not pd.isna(df['atr_calc'].iloc[-1]) else 0.0
        else:
            atr_14 = float(atr_14)
            
        # Calculate Bollinger Bandwidth
        bb_bandwidth = 0.0
        if bb_middle > 0:
            bb_bandwidth = float((bb_upper - bb_lower) / bb_middle)
            
        # Volatility proxy: Relative ATR
        relative_atr = 0.0
        if close_price > 0:
            relative_atr = float(atr_14 / close_price)
            
        # Classify regime
        if adx < 25.0 or bb_bandwidth < 0.015:
            regime = "SIDEWAYS"
        else:
            # Trending
            if sma_20 > sma_50:
                regime = "TRENDING_UP"
            elif sma_20 < sma_50:
                regime = "TRENDING_DOWN"
            else:
                # Fallback to BB middle
                if close_price > bb_middle:
                    regime = "TRENDING_UP"
                elif close_price < bb_middle:
                    regime = "TRENDING_DOWN"
                else:
                    regime = "SIDEWAYS"
                    
        return {
            "regime": regime,
            "adx": adx,
            "bb_bandwidth": bb_bandwidth,
            "relative_atr": relative_atr,
        }
    except Exception as e:
        logger.error(f"Error calculating market regime: {e}", exc_info=True)
        return {
            "regime": "SIDEWAYS",
            "adx": 0.0,
            "bb_bandwidth": 0.0,
            "relative_atr": 0.0,
        }
