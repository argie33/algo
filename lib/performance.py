"""
Performance calculation utilities - shared across all data loaders
Eliminates duplication of performance calculations and indicators
"""

import numpy as np
import logging
from typing import Optional, List, Tuple


def calculate_rsi(prices: np.ndarray, period: int = 14) -> Optional[float]:
    """
    Calculate Relative Strength Index (14-period standard)

    Args:
        prices: Array of closing prices
        period: RSI period (default: 14)

    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def calculate_performance_metrics(
    prices: np.ndarray, volumes: Optional[np.ndarray] = None
) -> dict:
    """
    Calculate 1-day, 5-day, and 20-day performance metrics

    Args:
        prices: Array of closing prices
        volumes: Optional array of volumes

    Returns:
        dict: {perf_1d, perf_5d, perf_20d, current_price, current_volume}
    """
    if len(prices) < 2:
        return {
            "perf_1d": 0.0,
            "perf_5d": 0.0,
            "perf_20d": 0.0,
            "current_price": float(prices[-1]),
            "current_volume": 0,
        }

    current_price = prices[-1]
    prev_price = prices[-2]

    perf_1d = ((current_price - prev_price) / prev_price * 100) if prev_price > 0 else 0
    perf_5d = (
        ((current_price - prices[-6]) / prices[-6] * 100) if len(prices) >= 6 else 0
    )
    perf_20d = (
        ((current_price - prices[-21]) / prices[-21] * 100) if len(prices) >= 21 else 0
    )

    current_volume = 0
    if volumes is not None and len(volumes) > 0:
        current_volume = int(volumes[-1])

    return {
        "perf_1d": float(perf_1d),
        "perf_5d": float(perf_5d),
        "perf_20d": float(perf_20d),
        "current_price": float(current_price),
        "current_volume": current_volume,
    }


def calculate_moving_averages(prices: np.ndarray) -> dict:
    """
    Calculate SMA-50 and SMA-200

    Args:
        prices: Array of closing prices

    Returns:
        dict: {sma_50, sma_200}
    """
    sma_50 = float(np.mean(prices[-50:])) if len(prices) >= 50 else None
    sma_200 = float(np.mean(prices[-200:])) if len(prices) >= 200 else None

    return {
        "sma_50": sma_50,
        "sma_200": sma_200,
    }


def calculate_momentum(perf_1d: float, perf_5d: float, perf_20d: float) -> str:
    """
    Determine momentum (Strong/Moderate/Weak)
    Based on multi-period performance acceleration

    Args:
        perf_1d: 1-day performance %
        perf_5d: 5-day performance %
        perf_20d: 20-day performance %

    Returns:
        str: 'Strong', 'Moderate', or 'Weak'
    """
    # Strong: All positive with acceleration
    if perf_1d > 0 and perf_5d > 0 and perf_20d > 0:
        if perf_1d > perf_5d / 5 and perf_5d > perf_20d / 4:
            return "Strong"

    # Weak: All negative with deceleration
    if perf_1d < 0 and perf_5d < 0 and perf_20d < 0:
        if perf_1d < perf_5d / 5 and perf_5d < perf_20d / 4:
            return "Weak"

    return "Moderate"


def calculate_trend(perf_5d: float, perf_20d: float) -> str:
    """
    Determine trend direction (Uptrend/Downtrend/Sideways)

    Args:
        perf_5d: 5-day performance %
        perf_20d: 20-day performance %

    Returns:
        str: 'Uptrend', 'Downtrend', or 'Sideways'
    """
    if perf_5d > 1 and perf_20d > 2:
        return "Uptrend"
    elif perf_5d < -1 and perf_20d < -2:
        return "Downtrend"
    else:
        return "Sideways"


def calculate_money_flow(volume: List[float], prices: List[float]) -> str:
    """
    Determine money flow (Inflow/Outflow/Neutral)
    Based on Chaikin Money Flow concept

    Args:
        volume: List of volumes
        prices: List of prices

    Returns:
        str: 'Inflow', 'Outflow', or 'Neutral'
    """
    if len(volume) < 20 or len(prices) < 20:
        return "Neutral"

    recent_vol = volume[-20:]
    recent_prices = prices[-20:]

    up_volume = 0
    down_volume = 0

    for i in range(1, len(recent_prices)):
        if recent_prices[i] > recent_prices[i - 1]:
            up_volume += recent_vol[i]
        elif recent_prices[i] < recent_prices[i - 1]:
            down_volume += recent_vol[i]

    total_volume = up_volume + down_volume
    if total_volume == 0:
        return "Neutral"

    ratio = up_volume / total_volume

    if ratio > 0.55:
        return "Inflow"
    elif ratio < 0.45:
        return "Outflow"
    else:
        return "Neutral"
