#!/usr/bin/env python3
"""Shared technical indicator computations for loaders.

Eliminates duplication: signal loaders, metric loaders, and filters all use
the same indicator calculations from a single source.
"""

import numpy as np
import pandas as pd

from utils.data.tick_validator import TickValidator


def detect_and_adjust_splits(df: pd.DataFrame) -> pd.DataFrame:
    """Back-adjust one symbol's OHLCV for stock splits before computing indicators.

    price_daily stores raw/unadjusted prices (see utils/external/alpaca_market_data.py -
    ALPACA_DATA_ADJUSTMENT defaults to "raw"). A real stock split therefore shows up as a
    permanent step in the close series - e.g. a 2:1 split reads as a fake -50% single-day
    return - which every trailing-window indicator computed downstream (RSI, MACD, moving
    averages, ATR, Bollinger Bands, and the roc_10d..roc_252d momentum columns) then carries
    for as long as the split date sits inside that indicator's lookback window (up to 252
    calendar days for roc_252d). Nothing upstream corrects this: tick_validator.py only
    stops the split-day gap from being rejected as bad data at ingestion, and
    position_monitor.py only fixes the quantity/stop of a currently open position - neither
    adjusts the stored historical series.

    This detects splits the same way tick_validator.py does (a close-to-close ratio matching
    one of TickValidator._SPLIT_RATIOS within its tolerance) and multiplies every row BEFORE
    the split by the inverse ratio (dividing volume by the same factor), so the indicator
    functions below see a continuous series. Does not modify the stored price_daily table -
    this is an in-memory adjustment applied only for indicator computation.

    Args:
        df: Single symbol's OHLCV rows, sorted ascending by date, with columns
            open/high/low/close and optionally volume. Not mutated in place.

    Returns:
        Adjusted copy of df (or df unchanged if no split detected).

    Caveat shared with tick_validator.py: a genuine single-day crash (e.g. delisting,
    fraud) that happens to land within 2% of a clean split ratio (2, 3, 4, 5, 10, ...) will
    be misread as a split and have its history incorrectly halved/etc rather than left
    alone. This is the same trade-off tick_validator.py already accepts to avoid rejecting
    legitimate split data at ingestion.
    """
    close = df["close"]
    n = len(close)
    if n < 2:
        return df

    prior = close.shift(1)
    factor = 1.0
    cumulative_factor = [1.0] * n
    for i in range(n - 1, 0, -1):
        prior_close = prior.iloc[i]
        cur_close = close.iloc[i]
        if pd.notna(prior_close) and prior_close > 0 and pd.notna(cur_close) and cur_close > 0:
            canonical_ratio = _match_split_ratio(prior_close / cur_close)
            if canonical_ratio is not None:
                factor /= canonical_ratio
        cumulative_factor[i - 1] = factor

    if all(f == 1.0 for f in cumulative_factor):
        return df

    df = df.copy()
    adj = pd.Series(cumulative_factor, index=df.index)
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            df[col] = df[col] * adj
    if "volume" in df.columns:
        df["volume"] = (df["volume"] / adj).round()
    return df


def _match_split_ratio(ratio: float) -> float | None:
    """Snap an observed prior_close/close ratio to the nearest canonical split ratio.

    Returns the canonical ratio (e.g. 2.0 for a 2:1 forward split, 0.1 for a 1:10 reverse
    split), not the noisy observed value, so an ordinary same-day price move layered on top
    of the split doesn't get baked into the historical adjustment factor. Uses the same
    ratio table and tolerance as tick_validator.py's split detector so a price move is
    treated as a split here if and only if ingestion would also have accepted it as one.
    """
    for candidate in TickValidator._SPLIT_RATIOS:
        if abs(ratio - candidate) / candidate <= TickValidator._SPLIT_RATIO_TOLERANCE:
            return float(candidate)
        inverse = 1 / candidate
        if abs(ratio - inverse) / inverse <= TickValidator._SPLIT_RATIO_TOLERANCE:
            return float(inverse)
    return None


def compute_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Compute Relative Strength Index using Wilder's EMA smoothing.

    GOVERNANCE: If price data is missing (NaN), RSI becomes NaN instead of silently
    defaulting to a calculated value. This preserves data quality visibility.
    """
    deltas = closes.diff()
    # Textbook Wilder's RSI: gain/loss for EVERY day, 0 on days that don't qualify (a down
    # day contributes 0 to the gain average, not "excluded from it"; symmetric for losses).
    # This previously used deltas.where(...>0, np.nan) instead of .clip() - masking
    # non-qualifying days as NaN and letting .ewm().mean() skip them, which computes something
    # structurally different from RSI: "average gain per up-day" decayed over up-days only,
    # rather than "average gain per day" decayed over calendar time (with down-days
    # contributing zero). The two are not close - live-measured mean ~10.9 / max ~44.6 point
    # divergence on a 0-100 scale, and the NaN-skip version doesn't produce its first value
    # until ~2x the documented period (needs `period` up-days, not `period` calendar days).
    # NaN closes (genuinely missing price data, not "no gain today") still propagate as NaN
    # through .clip(), preserving the GOVERNANCE behavior above.
    gains = deltas.clip(lower=0)
    losses = -deltas.clip(upper=0)
    # adjust=False for true Wilder's recursive smoothing (y_t = alpha*x_t + (1-alpha)*y_{t-1},
    # alpha=1/period) - the same convention compute_atr/compute_adx below use and document
    # ("NOT a simple rolling mean").
    avg_gain = gains.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # avg_loss==0 (no losses anywhere in the decayed history) makes RS infinite / rsi's
    # division above NaN via the replace(0, NaN) guard - textbook RSI defines this as the
    # extreme (100), not undefined, and symmetrically for avg_gain==0 -> RSI=0. Both being
    # exactly 0 (avg_gain==0 and avg_loss==0, i.e. a perfectly flat run of closes) is
    # genuinely undefined (0/0) and stays NaN rather than guessing 50.
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    rsi = rsi.where(~((avg_loss == 0) & ~both_zero), 100.0)
    rsi = rsi.where(~((avg_gain == 0) & ~both_zero), 0.0)
    return rsi


def compute_macd(
    closes: pd.Series, fast: int = 12, slow: int = 26, signal_period: int = 9
) -> tuple[pd.Series, pd.Series]:
    """Compute MACD line and signal line using the standard recursive EMA.

    adjust=False, matching the recursive smoothing this file already uses for RSI/ATR/ADX
    (see compute_rsi's comment) and the textbook MACD definition
    (EMA_t = alpha*price_t + (1-alpha)*EMA_{t-1}). Pandas' default (adjust=True) computes a
    finite-history-weighted average instead, which is a materially different number early in
    a series - measured ~0.19 absolute divergence at bar 12 and still ~0.06 at bar 29 on a
    synthetic 30-bar series, converging only slowly - most relevant for newly-added symbols
    or early trading history where a stock has limited price data.
    """
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    return macd_line, signal_line


def compute_moving_averages(closes: pd.Series) -> dict[str, pd.Series]:
    # adjust=False on the EMA columns for the same reason as compute_macd above: the
    # recursive EMA is the standard convention (and what RSI/ATR/ADX in this file already
    # use), while pandas' default (adjust=True) is a materially different, finite-history-
    # weighted number - most divergent on symbols with limited trading history. ema_21 isn't
    # just a display column: exit_engine.py gates a real distribution-day exit trigger on
    # `cur_price < ema_21`, so an inaccurate value here can bias a live trading decision, not
    # just a chart.
    return {
        "sma_20": closes.rolling(20).mean(),
        "sma_50": closes.rolling(50).mean(),
        "sma_150": closes.rolling(150).mean(),
        "sma_200": closes.rolling(200).mean(),
        "ema_12": closes.ewm(span=12, adjust=False).mean(),
        "ema_21": closes.ewm(span=21, adjust=False).mean(),
        "ema_26": closes.ewm(span=26, adjust=False).mean(),
    }


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Compute Average True Range using Wilder's exponential smoothing (alpha=1/period).

    Uses the same Wilder's EMA as RSI and ADX - NOT a simple rolling mean.
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
    sma = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    return {
        "bb_middle": sma,
        "bb_upper": sma + (std * std_dev),
        "bb_lower": sma - (std * std_dev),
    }


def compute_volume_ma(volume: pd.Series, period: int = 50) -> pd.Series:
    return volume.rolling(period).mean()


def compute_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
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


