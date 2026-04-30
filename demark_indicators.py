#!/usr/bin/env python3
"""
DeMark TD Sequential Indicator Library
Computes Tom DeMark's TD Setup, Countdown, Perfection, and Pressure indicators.
Used across range trading, mean reversion, and other strategies.
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


def compute_td_buy_setup(close: pd.Series) -> pd.Series:
    """
    TD Buy Setup counter (0-9, repeating).
    Increments when close[t] < close[t-4], resets otherwise.
    Value 9 indicates setup complete (potential bottom exhaustion).
    """
    if len(close) < 5:
        return pd.Series([0] * len(close), index=close.index)

    setup_count = pd.Series(0, index=close.index, dtype=int)

    for i in range(4, len(close)):
        if close.iloc[i] < close.iloc[i-4]:
            # Increment count
            setup_count.iloc[i] = setup_count.iloc[i-1] + 1 if setup_count.iloc[i-1] > 0 else 1
        else:
            # Reset on any close >= close[t-4]
            setup_count.iloc[i] = 0

    return setup_count


def compute_td_sell_setup(close: pd.Series) -> pd.Series:
    """
    TD Sell Setup counter (0-9, repeating).
    Increments when close[t] > close[t-4], resets otherwise.
    Value 9 indicates setup complete (potential top exhaustion).
    """
    if len(close) < 5:
        return pd.Series([0] * len(close), index=close.index)

    setup_count = pd.Series(0, index=close.index, dtype=int)

    for i in range(4, len(close)):
        if close.iloc[i] > close.iloc[i-4]:
            # Increment count
            setup_count.iloc[i] = setup_count.iloc[i-1] + 1 if setup_count.iloc[i-1] > 0 else 1
        else:
            # Reset on any close <= close[t-4]
            setup_count.iloc[i] = 0

    return setup_count


def compute_td_buy_setup_perfected(low: pd.Series, high: pd.Series, buy_setup_count: pd.Series) -> pd.Series:
    """
    TD Buy Setup Perfected flag.
    True when buy_setup_count == 9 AND (low[t-2] OR low[t-3]) <= min(low[t-7:t-5]).
    Indicates stronger/confirmed bottom exhaustion.
    """
    if len(low) < 9:
        return pd.Series(False, index=low.index)

    perfected = pd.Series(False, index=low.index)

    for i in range(8, len(low)):
        if buy_setup_count.iloc[i] == 9:
            # Check if low[t-2] or low[t-3] is below the range low[t-7:t-5]
            recent_low = min(low.iloc[i-2], low.iloc[i-3])
            prior_low = min(low.iloc[i-7:i-4])

            if recent_low <= prior_low:
                perfected.iloc[i] = True

    return perfected


def compute_td_sell_setup_perfected(low: pd.Series, high: pd.Series, sell_setup_count: pd.Series) -> pd.Series:
    """
    TD Sell Setup Perfected flag.
    True when sell_setup_count == 9 AND (high[t-2] OR high[t-3]) >= max(high[t-7:t-5]).
    Indicates stronger/confirmed top exhaustion.
    """
    if len(high) < 9:
        return pd.Series(False, index=high.index)

    perfected = pd.Series(False, index=high.index)

    for i in range(8, len(high)):
        if sell_setup_count.iloc[i] == 9:
            # Check if high[t-2] or high[t-3] is above the range high[t-7:t-5]
            recent_high = max(high.iloc[i-2], high.iloc[i-3])
            prior_high = max(high.iloc[i-7:i-4])

            if recent_high >= prior_high:
                perfected.iloc[i] = True

    return perfected


def compute_td_buy_countdown(low: pd.Series, close: pd.Series, buy_setup_complete: pd.Series) -> pd.Series:
    """
    TD Buy Countdown counter (0-13).
    After buy_setup_complete fires (count==9), count bars where close[t] <= low[t-2].
    Resets if price closes above setup high before reaching 13.
    """
    if len(close) < 3:
        return pd.Series(0, index=close.index, dtype=int)

    countdown = pd.Series(0, index=close.index, dtype=int)
    setup_high_at_9 = None
    in_countdown = False

    for i in range(2, len(close)):
        if buy_setup_complete.iloc[i] and not in_countdown:
            # Start countdown
            in_countdown = True
            setup_high_at_9 = close.iloc[i:i+1].max()

        if in_countdown:
            if close.iloc[i] <= low.iloc[i-2]:
                countdown.iloc[i] = countdown.iloc[i-1] + 1

                if countdown.iloc[i] >= 13:
                    in_countdown = False
            else:
                countdown.iloc[i] = countdown.iloc[i-1]

    return countdown


def compute_td_sell_countdown(high: pd.Series, close: pd.Series, sell_setup_complete: pd.Series) -> pd.Series:
    """
    TD Sell Countdown counter (0-13).
    After sell_setup_complete fires (count==9), count bars where close[t] >= high[t-2].
    Resets if price closes below setup low before reaching 13.
    """
    if len(close) < 3:
        return pd.Series(0, index=close.index, dtype=int)

    countdown = pd.Series(0, index=close.index, dtype=int)
    setup_low_at_9 = None
    in_countdown = False

    for i in range(2, len(close)):
        if sell_setup_complete.iloc[i] and not in_countdown:
            # Start countdown
            in_countdown = True
            setup_low_at_9 = close.iloc[i:i+1].min()

        if in_countdown:
            if close.iloc[i] >= high.iloc[i-2]:
                countdown.iloc[i] = countdown.iloc[i-1] + 1

                if countdown.iloc[i] >= 13:
                    in_countdown = False
            else:
                countdown.iloc[i] = countdown.iloc[i-1]

    return countdown


def compute_td_pressure(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 5) -> pd.Series:
    """
    TD Pressure = average buying pressure over period.
    Formula: (close - low) / (high - low) for each bar, then avg over period.
    Range: 0 (extreme selling) to 1 (extreme buying).
    Normalized to 0-100 scale.
    """
    if len(close) < period:
        return pd.Series(0.0, index=close.index)

    # Avoid division by zero
    range_hlc = high - low
    range_hlc = range_hlc.replace(0, np.nan)

    # Pressure for each bar
    pressure_bar = (close - low) / range_hlc
    pressure_bar = pressure_bar.fillna(0.5)  # If high==low, assume neutral

    # Rolling average over period
    pressure_rolling = pressure_bar.rolling(window=period).mean()

    # Normalize to 0-100
    pressure_normalized = pressure_rolling * 100

    return pressure_normalized.fillna(0)


def compute_bars_since_td9_buy(buy_setup_complete: pd.Series) -> pd.Series:
    """
    Count bars since last TD Buy Setup 9 completed.
    Useful for measuring recency of reversal signal.
    """
    bars_since = pd.Series(0, index=buy_setup_complete.index, dtype=int)
    last_td9_bar = -999

    for i, val in enumerate(buy_setup_complete):
        if val:
            last_td9_bar = i
        bars_since.iloc[i] = i - last_td9_bar

    return bars_since


def compute_bars_since_td9_sell(sell_setup_complete: pd.Series) -> pd.Series:
    """
    Count bars since last TD Sell Setup 9 completed.
    """
    bars_since = pd.Series(0, index=sell_setup_complete.index, dtype=int)
    last_td9_bar = -999

    for i, val in enumerate(sell_setup_complete):
        if val:
            last_td9_bar = i
        bars_since.iloc[i] = i - last_td9_bar

    return bars_since


def compute_all_td_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all DeMark TD indicators for a dataframe.

    Input: DataFrame with columns: open, high, low, close
    Output: DataFrame with added TD columns

    New columns:
    - td_buy_setup_count: 0-9 repeating
    - td_sell_setup_count: 0-9 repeating
    - td_buy_setup_complete: boolean (count == 9)
    - td_sell_setup_complete: boolean (count == 9)
    - td_buy_setup_perfected: boolean
    - td_sell_setup_perfected: boolean
    - td_buy_countdown_count: 0-13
    - td_sell_countdown_count: 0-13
    - td_pressure: 0-100 numeric
    - bars_since_td9_buy: integer
    - bars_since_td9_sell: integer
    """
    df = df.copy()

    try:
        # Setup counts
        df['td_buy_setup_count'] = compute_td_buy_setup(df['close'])
        df['td_sell_setup_count'] = compute_td_sell_setup(df['close'])

        # Setup completion flags
        df['td_buy_setup_complete'] = (df['td_buy_setup_count'] == 9)
        df['td_sell_setup_complete'] = (df['td_sell_setup_count'] == 9)

        # Perfection flags
        df['td_buy_setup_perfected'] = compute_td_buy_setup_perfected(
            df['low'], df['high'], df['td_buy_setup_count']
        )
        df['td_sell_setup_perfected'] = compute_td_sell_setup_perfected(
            df['low'], df['high'], df['td_sell_setup_count']
        )

        # Countdown counts
        df['td_buy_countdown_count'] = compute_td_buy_countdown(
            df['low'], df['close'], df['td_buy_setup_complete']
        )
        df['td_sell_countdown_count'] = compute_td_sell_countdown(
            df['high'], df['close'], df['td_sell_setup_complete']
        )

        # Pressure
        df['td_pressure'] = compute_td_pressure(
            df['open'], df['high'], df['low'], df['close']
        )

        # Bars since
        df['bars_since_td9_buy'] = compute_bars_since_td9_buy(df['td_buy_setup_complete'])
        df['bars_since_td9_sell'] = compute_bars_since_td9_sell(df['td_sell_setup_complete'])

        return df

    except Exception as e:
        logger.error(f"Error computing TD indicators: {e}")
        # Return with zero columns if error
        for col in ['td_buy_setup_count', 'td_sell_setup_count', 'td_buy_setup_complete',
                    'td_sell_setup_complete', 'td_buy_setup_perfected', 'td_sell_setup_perfected',
                    'td_buy_countdown_count', 'td_sell_countdown_count', 'td_pressure',
                    'bars_since_td9_buy', 'bars_since_td9_sell']:
            df[col] = 0 if 'count' in col or 'pressure' in col else False
        return df
