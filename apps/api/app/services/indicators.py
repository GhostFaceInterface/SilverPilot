import numpy as np
import pandas as pd


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes technical indicators for a given DataFrame of prices.
    Required columns: high, low, close.
    All calculations are done native USD.
    Uses pure pandas to avoid numba / pandas-ta compile dependencies on Python 3.14+.
    """
    df = df.copy()
    if df.empty or len(df) < 2:
        # Not enough data to compute indicators, fill with None
        for col in [
            "rsi_14",
            "macd_line",
            "macd_signal",
            "macd_histogram",
            "bb_upper_20_2",
            "bb_middle_20_2",
            "bb_lower_20_2",
            "sma_20",
            "sma_50",
            "sma_200",
            "ema_20",
            "ema_50",
            "ema_200",
            "adx_14",
            "plus_di_14",
            "minus_di_14",
            "bb_bandwidth_20_2",
            "bb_percent_b_20_2",
            "atr_percent_14",
            "rsi_slope_1",
            "macd_histogram_slope_1",
            "atr_14",
        ]:
            df[col] = None
        return df

    # Helper math functions
    def get_sma(series, length):
        return series.rolling(window=length).mean()

    def get_ema(series, length):
        return series.ewm(span=length, adjust=False).mean()

    # RSI 14
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()
    rs = avg_gain / avg_loss
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    try:
        ema_fast = get_ema(df["close"], 12)
        ema_slow = get_ema(df["close"], 26)
        df["macd_line"] = ema_fast - ema_slow
        df["macd_signal"] = get_ema(df["macd_line"], 9)
        df["macd_histogram"] = df["macd_line"] - df["macd_signal"]
    except Exception:
        df["macd_line"] = None
        df["macd_signal"] = None
        df["macd_histogram"] = None

    # Bollinger Bands (20, 2)
    try:
        sma20 = get_sma(df["close"], 20)
        rstd = df["close"].rolling(window=20).std()
        df["bb_upper_20_2"] = sma20 + (2 * rstd)
        df["bb_middle_20_2"] = sma20
        df["bb_lower_20_2"] = sma20 - (2 * rstd)
        df["bb_bandwidth_20_2"] = (df["bb_upper_20_2"] - df["bb_lower_20_2"]) / df["bb_middle_20_2"].replace(0, np.nan)
        df["bb_percent_b_20_2"] = (df["close"] - df["bb_lower_20_2"]) / (
            (df["bb_upper_20_2"] - df["bb_lower_20_2"]).replace(0, np.nan)
        )
    except Exception:
        df["bb_upper_20_2"] = None
        df["bb_middle_20_2"] = None
        df["bb_lower_20_2"] = None
        df["bb_bandwidth_20_2"] = None
        df["bb_percent_b_20_2"] = None

    # SMAs (20, 50, 200)
    df["sma_20"] = get_sma(df["close"], 20)
    df["sma_50"] = get_sma(df["close"], 50)
    df["sma_200"] = get_sma(df["close"], 200)
    df["ema_20"] = get_ema(df["close"], 20)
    df["ema_50"] = get_ema(df["close"], 50)
    df["ema_200"] = get_ema(df["close"], 200)

    # ATR 14
    try:
        h_l = df["high"] - df["low"]
        h_pc = (df["high"] - df["close"].shift(1)).abs()
        l_pc = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        df["atr_14"] = tr.ewm(alpha=1 / 14, min_periods=14).mean()
        df["atr_percent_14"] = df["atr_14"] / df["close"].replace(0, np.nan)
    except Exception:
        df["atr_14"] = None
        df["atr_percent_14"] = None

    # ADX / DI (14)
    try:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)
        prev_high = high.shift(1)
        prev_low = low.shift(1)

        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        plus_dm = ((high - prev_high) > (prev_low - low)) & ((high - prev_high) > 0)
        minus_dm = ((prev_low - low) > (high - prev_high)) & ((prev_low - low) > 0)

        plus_dm = (high - prev_high).where(plus_dm, 0.0)
        minus_dm = (prev_low - low).where(minus_dm, 0.0)

        tr_smoothed = tr.ewm(alpha=1 / 14, min_periods=14).mean()
        plus_dm_smoothed = plus_dm.ewm(alpha=1 / 14, min_periods=14).mean()
        minus_dm_smoothed = minus_dm.ewm(alpha=1 / 14, min_periods=14).mean()

        df["plus_di_14"] = (100 * (plus_dm_smoothed / tr_smoothed.replace(0, np.nan))).fillna(0.0)
        df["minus_di_14"] = (100 * (minus_dm_smoothed / tr_smoothed.replace(0, np.nan))).fillna(0.0)
        dx = 100 * (
            (df["plus_di_14"] - df["minus_di_14"]).abs() / (df["plus_di_14"] + df["minus_di_14"]).replace(0, np.nan)
        )
        df["adx_14"] = dx.fillna(0.0).ewm(alpha=1 / 14, min_periods=14).mean().fillna(0.0)
    except Exception:
        df["adx_14"] = None
        df["plus_di_14"] = None
        df["minus_di_14"] = None

    # Slopes for momentum confirmation
    df["rsi_slope_1"] = df["rsi_14"].diff()
    df["macd_histogram_slope_1"] = df["macd_histogram"].diff()

    return df
