"""Regression tests for split-adjustment in loaders/technical_indicators.py.

price_daily stores raw/unadjusted prices (ALPACA_DATA_ADJUSTMENT defaults to "raw" -
see utils/external/alpaca_market_data.py). Before this fix, nothing in the pipeline
adjusted historical prices for stock splits: a stock split showed up as a fake
~50%+ single-day move that every trailing-window indicator (RSI, MACD, moving
averages, ATR, Bollinger Bands, roc_10d..roc_252d) would carry until the split date
aged out of that indicator's lookback window - up to 252 calendar days for
roc_252d. detect_and_adjust_splits() back-adjusts the in-memory series before
indicators are computed from it (it does not rewrite the stored price_daily table).
"""

import pandas as pd
import pytest

from loaders.technical_indicators import (
    _match_split_ratio,
    compute_rsi,
    detect_and_adjust_splits,
)


def _ohlcv(closes: list[float], volumes: list[int] | None = None) -> pd.DataFrame:
    n = len(closes)
    if volumes is None:
        volumes = [1_000_000] * n
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=n, freq="D"),
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": volumes,
        }
    )


class TestMatchSplitRatio:
    def test_clean_2_for_1(self):
        assert _match_split_ratio(2.0) == 2.0

    def test_clean_1_for_10_reverse(self):
        assert _match_split_ratio(0.1) == pytest.approx(0.1)

    def test_within_tolerance(self):
        # 2:1 split with a small same-day move layered on top
        assert _match_split_ratio(1.99) == 2.0

    def test_ordinary_daily_move_not_a_split(self):
        assert _match_split_ratio(1.10) is None  # 10% daily move
        assert _match_split_ratio(0.85) is None  # -15% daily move


class TestDetectAndAdjustSplits:
    def test_2_for_1_forward_split_removes_fake_cliff(self):
        # Trading flat at $200, splits 2:1, then flat at $100 - no real economic move.
        closes = [200.0] * 5 + [100.0] * 5
        df = _ohlcv(closes)

        adjusted = detect_and_adjust_splits(df)

        # Pre-split rows rescaled to post-split terms; post-split rows untouched.
        assert adjusted["close"].iloc[:5].tolist() == pytest.approx([100.0] * 5)
        assert adjusted["close"].iloc[5:].tolist() == pytest.approx([100.0] * 5)
        # No fake day-over-day return remains at the former split boundary.
        returns = adjusted["close"].pct_change().dropna()
        assert returns.abs().max() < 0.01

    def test_volume_inverse_adjusted(self):
        closes = [200.0] * 3 + [100.0] * 3
        volumes = [1_000_000] * 3 + [2_000_000] * 3
        df = _ohlcv(closes, volumes)

        adjusted = detect_and_adjust_splits(df)

        # Pre-split share counts inflated to match the post-split share count basis.
        assert adjusted["volume"].iloc[:3].tolist() == pytest.approx([2_000_000] * 3)
        assert adjusted["volume"].iloc[3:].tolist() == pytest.approx([2_000_000] * 3)

    def test_reverse_split_1_for_10(self):
        # Distressed penny stock: $1 -> $10 via 1:10 reverse split, no real economic move.
        closes = [1.0] * 3 + [10.0] * 3
        df = _ohlcv(closes)

        adjusted = detect_and_adjust_splits(df)

        assert adjusted["close"].iloc[:3].tolist() == pytest.approx([10.0] * 3)

    def test_ordinary_volatility_not_adjusted(self):
        # A rough but not split-ratio-matching trading day should pass through unchanged.
        closes = [100.0, 102.0, 98.0, 105.0, 101.0]
        df = _ohlcv(closes)

        adjusted = detect_and_adjust_splits(df)

        assert adjusted["close"].tolist() == pytest.approx(closes)

    def test_genuine_crash_is_not_masked_when_ratio_does_not_match(self):
        # -40% single-day crash: not within tolerance of any clean split ratio, so it
        # must be left alone rather than silently rescaled.
        closes = [100.0, 100.0, 60.0, 60.0]
        df = _ohlcv(closes)

        adjusted = detect_and_adjust_splits(df)

        assert adjusted["close"].tolist() == pytest.approx(closes)

    def test_multiple_splits_compound(self):
        # 2:1 then later 3:1 (from the adjusted post-first-split basis): $600 -> $300 -> $100.
        closes = [600.0] * 2 + [300.0] * 2 + [100.0] * 2
        df = _ohlcv(closes)

        adjusted = detect_and_adjust_splits(df)

        assert adjusted["close"].tolist() == pytest.approx([100.0] * 6)

    def test_short_series_returns_unchanged(self):
        df = _ohlcv([100.0])
        adjusted = detect_and_adjust_splits(df)
        assert adjusted["close"].tolist() == [100.0]

    def test_no_split_returns_same_object_semantics(self):
        closes = [100.0, 101.0, 99.0, 102.0]
        df = _ohlcv(closes)
        adjusted = detect_and_adjust_splits(df)
        assert adjusted["close"].tolist() == pytest.approx(closes)


class TestRsiContinuityAcrossSplit:
    def test_rsi_has_no_extreme_reading_at_former_split_boundary(self):
        """Regression: RSI computed on raw (unadjusted) data reads as falsely oversold
        right at a split boundary because the fake single-day halving looks like a huge
        loss relative to the mild day-to-day noise around it. After adjustment, RSI
        around that date should reflect the actual mild uptrend, not the artificial
        split cliff."""
        import random

        rng = random.Random(42)
        price = 200.0
        pre_split = []
        for _ in range(30):
            price += rng.uniform(-2, 3)
            pre_split.append(round(price, 2))

        # Split 2:1: continue the same mild uptrend at the new (halved) price scale.
        price2 = pre_split[-1] / 2
        post_split = []
        for _ in range(30):
            price2 += rng.uniform(-1, 1.5)
            post_split.append(round(price2, 2))

        closes = pre_split + post_split
        df = _ohlcv(closes)

        raw_rsi = compute_rsi(df["close"], period=14)
        adjusted_df = detect_and_adjust_splits(df)
        adjusted_rsi = compute_rsi(adjusted_df["close"], period=14)

        boundary = len(pre_split)
        # Raw RSI right after the split falsely reads as oversold (the fake halving
        # dwarfs the ordinary day-to-day noise it's being averaged against).
        assert raw_rsi.iloc[boundary] < 20
        # Adjusted RSI reflects the real, continuous mild uptrend instead.
        assert 40 < adjusted_rsi.iloc[boundary] < 70
