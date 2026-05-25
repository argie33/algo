#!/usr/bin/env python3
"""Shared technical indicator computations for loaders.

Eliminates duplication: signal loaders, metric loaders, and filters all use
the same indicator calculations from a single source.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Any


def compute_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Compute Relative Strength Index using Wilder's EMA smoothing."""
    deltas = closes.diff()
    gains = deltas.where(deltas > 0, 0)
    losses = (-deltas.where(deltas < 0, 0))
    avg_gain = gains.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = losses.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal_period: int = 9) -> Tuple[pd.Series, pd.Series]:
    """Compute MACD line and signal line."""
    ema_fast = closes.ewm(span=fast).mean()
    ema_slow = closes.ewm(span=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period).mean()
    return macd_line, signal_line


def compute_moving_averages(closes: pd.Series) -> Dict[str, pd.Series]:
    """Compute all standard moving averages."""
    return {
        'sma_20': closes.rolling(20).mean(),
        'sma_50': closes.rolling(50).mean(),
        'sma_150': closes.rolling(150).mean(),
        'sma_200': closes.rolling(200).mean(),
        'ema_12': closes.ewm(span=12).mean(),
        'ema_21': closes.ewm(span=21).mean(),
        'ema_26': closes.ewm(span=26).mean(),
    }


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Compute Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr


def compute_bollinger_bands(closes: pd.Series, period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
    """Compute Bollinger Bands."""
    sma = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    return {
        'bb_middle': sma,
        'bb_upper': sma + (std * std_dev),
        'bb_lower': sma - (std * std_dev),
    }


def compute_volume_ma(volume: pd.Series, period: int = 50) -> pd.Series:
    """Compute volume moving average."""
    return volume.rolling(period).mean()


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators and add to dataframe.

    Input: DataFrame with columns [date, open, high, low, close, volume]
    Output: Same DataFrame with additional columns for all indicators
    """
    df = df.copy()

    # RSI
    df['rsi_14'] = compute_rsi(df['close'], 14)

    # MACD
    df['macd'], df['macd_signal'] = compute_macd(df['close'])

    # Moving Averages
    mas = compute_moving_averages(df['close'])
    for name, values in mas.items():
        df[name] = values

    # ATR
    df['atr_14'] = compute_atr(df['high'], df['low'], df['close'], 14)

    # Bollinger Bands
    bbs = compute_bollinger_bands(df['close'], 20, 2.0)
    for name, values in bbs.items():
        df[name] = values

    # Volume MA
    df['volume_ma_50'] = compute_volume_ma(df['volume'], 50)

    return df
