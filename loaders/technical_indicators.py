#!/usr/bin/env python3
"""Shared technical indicator computations for loaders.

Eliminates duplication: signal loaders, metric loaders, and filters all use
the same indicator calculations from a single source.
"""

import numpy as np
import pandas as pd


def compute_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Compute Relative Strength Index using Wilder's EMA smoothing."""
    deltas = closes.diff()
    gains = deltas.where(deltas > 0, 0)
    losses = -deltas.where(deltas < 0, 0)
    avg_gain = gains.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = losses.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(
    closes: pd.Series, fast: int = 12, slow: int = 26, signal_period: int = 9
) -> tuple[pd.Series, pd.Series]:
    """Compute MACD line and signal line."""
    ema_fast = closes.ewm(span=fast).mean()
    ema_slow = closes.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period).mean()
    return macd_line, signal_line


def compute_moving_averages(closes: pd.Series) -> dict[str, pd.Series]:
    """Compute all standard moving averages."""
    return {
        "sma_20": closes.rolling(20).mean(),
        "sma_50": closes.rolling(50).mean(),
        "sma_150": closes.rolling(150).mean(),
        "sma_200": closes.rolling(200).mean(),
        "ema_12": closes.ewm(span=12).mean(),
        "ema_21": closes.ewm(span=21).mean(),
        "ema_26": closes.ewm(span=26).mean(),
    }


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Compute Average True Range using Wilder's exponential smoothing (alpha=1/period).

    Uses the same Wilder's EMA as RSI and ADX — NOT a simple rolling mean.
    SMA would give discontinuous jumps as big days enter/exit the window.
    """
    # Reset frequency to avoid pandas frequency mismatch errors during operations
    high_reset = high.copy()
    low_reset = low.copy()
    close_reset = close.copy()
    if hasattr(high_reset.index, "freq") and high_reset.index.freq is not None:
        high_reset.index.freq = None
    if hasattr(low_reset.index, "freq") and low_reset.index.freq is not None:
        low_reset.index.freq = None
    if hasattr(close_reset.index, "freq") and close_reset.index.freq is not None:
        close_reset.index.freq = None

    tr1 = high_reset - low_reset
    tr2 = (high_reset - close_reset.shift()).abs()
    tr3 = (low_reset - close_reset.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return atr


def compute_bollinger_bands(closes: pd.Series, period: int = 20, std_dev: float = 2.0) -> dict[str, pd.Series]:
    """Compute Bollinger Bands."""
    sma = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    return {
        "bb_middle": sma,
        "bb_upper": sma + (std * std_dev),
        "bb_lower": sma - (std * std_dev),
    }


def compute_volume_ma(volume: pd.Series, period: int = 50) -> pd.Series:
    """Compute volume moving average."""
    return volume.rolling(period).mean()


def compute_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute Plus DI, Minus DI, and ADX using Wilder's smoothing.

    Returns: (plus_di, minus_di, adx)
    """
    # Reset frequency to avoid pandas frequency mismatch errors during operations
    high_reset = high.copy()
    low_reset = low.copy()
    close_reset = close.copy()
    if hasattr(high_reset.index, "freq") and high_reset.index.freq is not None:
        high_reset.index.freq = None
    if hasattr(low_reset.index, "freq") and low_reset.index.freq is not None:
        low_reset.index.freq = None
    if hasattr(close_reset.index, "freq") and close_reset.index.freq is not None:
        close_reset.index.freq = None

    high_diff = high_reset.diff()
    low_diff = -low_reset.diff()

    plus_dm = pd.Series(
        np.where((high_diff > 0) & (high_diff > low_diff), high_diff, 0.0),
        index=high_reset.index,
    )
    minus_dm = pd.Series(
        np.where((low_diff > 0) & (low_diff > high_diff), low_diff, 0.0),
        index=high_reset.index,
    )

    tr1 = high_reset - low_reset
    tr2 = (high_reset - close_reset.shift()).abs()
    tr3 = (low_reset - close_reset.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    alpha = 1.0 / period
    atr_w = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_dm_w = plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    minus_dm_w = minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    plus_di = 100.0 * plus_dm_w / atr_w.replace(0, np.nan)
    minus_di = 100.0 * minus_dm_w / atr_w.replace(0, np.nan)

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    return plus_di, minus_di, adx


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators and add to dataframe.

    Input: DataFrame with columns [date, open, high, low, close, volume]
    Output: Same DataFrame with additional columns for all indicators
    """
    df = df.copy()

    # RSI
    df["rsi_14"] = compute_rsi(df["close"], 14)

    # MACD
    df["macd"], df["macd_signal"] = compute_macd(df["close"])

    # Moving Averages
    mas = compute_moving_averages(df["close"])
    for name, values in mas.items():
        df[name] = values

    # ATR
    df["atr_14"] = compute_atr(df["high"], df["low"], df["close"], 14)

    # Bollinger Bands
    bbs = compute_bollinger_bands(df["close"], 20, 2.0)
    for name, values in bbs.items():
        df[name] = values

    # Volume MA
    df["volume_ma_50"] = compute_volume_ma(df["volume"], 50)

    return df
