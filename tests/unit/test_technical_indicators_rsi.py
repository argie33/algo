#!/usr/bin/env python3
"""Regression test for loaders/technical_indicators.py::compute_rsi using true Wilder's
RSI: every day contributes to the gain/loss averages (0 on non-qualifying days), smoothed
with adjust=False recursive EMA. Guards against reintroducing the NaN-masking bug, where
non-qualifying days were excluded from the average entirely instead of contributing 0."""

import numpy as np
import pandas as pd

from loaders.technical_indicators import compute_rsi


def _reference_wilder_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Independent reference implementation: seed with a plain SMA of the first `period`
    gains/losses, then Wilder's textbook recursive formula. Deliberately not vectorized /
    not using pandas .ewm(), so it validates compute_rsi against the formula itself."""
    deltas = closes.diff()
    gains = deltas.clip(lower=0)
    losses = -deltas.clip(upper=0)

    avg_gain = pd.Series(np.nan, index=closes.index)
    avg_loss = pd.Series(np.nan, index=closes.index)

    seed_idx = period  # first index with `period` deltas available (index 0 has none)
    avg_gain.iloc[seed_idx] = gains.iloc[1 : seed_idx + 1].mean()
    avg_loss.iloc[seed_idx] = losses.iloc[1 : seed_idx + 1].mean()

    for i in range(seed_idx + 1, len(closes)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gains.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + losses.iloc[i]) / period

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


class TestComputeRsiMatchesWildersFormula:
    def test_converges_to_reference_wilder_implementation(self):
        # The reference seeds with a plain SMA at index=period; compute_rsi seeds the ewm
        # recursion from the first observation. The seeding gap decays by a factor of
        # ((period-1)/period) per step - for period=14 that's <1% residual after ~65 steps -
        # so compare only once enough periods have elapsed for it to become negligible.
        rng = np.random.default_rng(42)
        closes = pd.Series(100 + np.cumsum(rng.normal(0, 1.5, 160)))

        actual = compute_rsi(closes)
        expected = _reference_wilder_rsi(closes)

        compare = pd.concat([actual, expected], axis=1).dropna().iloc[70:]
        assert len(compare) > 30
        max_diff = (compare.iloc[:, 0] - compare.iloc[:, 1]).abs().max()
        assert max_diff < 0.5, f"compute_rsi diverges from Wilder's formula by {max_diff}"

    def test_first_value_appears_at_documented_period_not_double(self):
        # Regression guard for the NaN-masking bug: that version needed ~2x the period
        # (roughly `period` up-days, which takes ~2*period calendar days) before RSI had
        # its first value, instead of the documented `period` calendar days.
        closes = pd.Series(100 + np.cumsum(np.sin(np.arange(40)) * 2))
        r = compute_rsi(closes, period=14)
        first_valid = r.first_valid_index()
        assert first_valid is not None
        assert first_valid <= 15, f"RSI first value at index {first_valid}, expected ~14"

    def test_does_not_match_naive_nan_masking_calculation(self):
        """Regression guard: this is what the bug looked like. If NaN-masking is
        reintroduced, this test fails (actual would then equal the buggy series)."""
        rng = np.random.default_rng(7)
        closes = pd.Series(100 + np.cumsum(rng.normal(0, 1.5, 100)))

        deltas = closes.diff()
        buggy_gains = deltas.where(deltas > 0, np.nan)
        buggy_losses = -deltas.where(deltas < 0, np.nan)
        buggy_avg_gain = buggy_gains.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
        buggy_avg_loss = buggy_losses.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
        buggy_rsi = 100 - (100 / (1 + buggy_avg_gain / buggy_avg_loss.replace(0, np.nan)))

        actual = compute_rsi(closes)
        compare = pd.concat([actual, buggy_rsi], axis=1).dropna()
        assert len(compare) > 30
        mean_diff = (compare.iloc[:, 0] - compare.iloc[:, 1]).abs().mean()
        assert mean_diff > 3.0, "compute_rsi should diverge meaningfully from the NaN-masking calculation"

    def test_bounded_zero_to_hundred(self):
        rng = np.random.default_rng(3)
        closes = pd.Series(100 + np.cumsum(rng.normal(0, 2.0, 100)))
        r = compute_rsi(closes)
        assert r.dropna().between(0, 100).all()

    def test_all_up_days_gives_rsi_100(self):
        closes = pd.Series(range(100, 130))  # strictly increasing every day
        r = compute_rsi(closes)
        assert r.dropna().iloc[-1] == 100.0

    def test_all_down_days_gives_rsi_0(self):
        closes = pd.Series(range(130, 100, -1))  # strictly decreasing every day
        r = compute_rsi(closes)
        assert r.dropna().iloc[-1] == 0.0

    def test_missing_price_data_propagates_as_nan(self):
        closes = pd.Series([100.0, 101.0, np.nan, 103.0] + [100 + i * 0.5 for i in range(20)])
        r = compute_rsi(closes, period=5)
        # RSI at/soon after the NaN close must not silently produce a numeric value from
        # partial/corrupted data
        assert pd.isna(r.iloc[2])
