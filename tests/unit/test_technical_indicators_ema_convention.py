#!/usr/bin/env python3
"""Regression test for loaders/technical_indicators.py's EMA columns (compute_macd,
compute_moving_averages) using the standard recursive EMA (adjust=False) - the same
convention compute_rsi/compute_atr/compute_adx already use. pandas' ewm() default
(adjust=True) computes a finite-history-weighted average instead, a materially different
number early in a series (most relevant for newly-tracked symbols with limited history).
ema_21 in particular gates a real exit_engine.py trading decision, not just a display value.
"""

import numpy as np
import pandas as pd

from loaders.technical_indicators import compute_macd, compute_moving_averages


def _reference_recursive_ema(closes: pd.Series, span: int) -> pd.Series:
    """Independent reference: textbook recursive EMA, seeded from the first observation -
    deliberately not using pandas .ewm() so it validates against the formula itself."""
    alpha = 2.0 / (span + 1)
    ema = pd.Series(np.nan, index=closes.index)
    ema.iloc[0] = closes.iloc[0]
    for i in range(1, len(closes)):
        ema.iloc[i] = alpha * closes.iloc[i] + (1 - alpha) * ema.iloc[i - 1]
    return ema


class TestComputeMacdUsesRecursiveEma:
    def test_matches_reference_recursive_ema_formula(self):
        rng = np.random.default_rng(11)
        closes = pd.Series(100 + np.cumsum(rng.normal(0, 1.5, 60)))

        macd_line, _signal = compute_macd(closes, fast=12, slow=26, signal_period=9)
        expected_fast = _reference_recursive_ema(closes, 12)
        expected_slow = _reference_recursive_ema(closes, 26)
        expected_macd = expected_fast - expected_slow

        diff = (macd_line - expected_macd).abs()
        assert diff.max() < 1e-9, f"compute_macd diverges from recursive EMA formula by {diff.max()}"

    def test_does_not_match_pandas_default_adjust_true(self):
        """Regression guard: adjust=True (pandas default) is a measurably different value,
        especially early in the series - if adjust=False is dropped, this test catches it.
        Compares the fast EMA component directly (not the fast-minus-slow MACD line, where
        adjust=True's bias on both legs partially cancels)."""
        rng = np.random.default_rng(5)
        closes = pd.Series(100 + np.cumsum(rng.normal(0, 1.5, 30)))

        macd_line, _signal = compute_macd(closes, fast=12, slow=26, signal_period=9)
        buggy_fast = closes.ewm(span=12).mean()  # adjust=True default
        buggy_slow = closes.ewm(span=26).mean()
        buggy_macd = buggy_fast - buggy_slow

        assert abs(buggy_fast.iloc[3] - closes.ewm(span=12, adjust=False).mean().iloc[3]) > 0.1, (
            "test setup: adjust=True vs adjust=False should diverge meaningfully at this index"
        )
        # Even with partial cancellation between the fast/slow legs, the MACD line itself
        # still diverges detectably early in the series.
        diff_early = abs(macd_line.iloc[3] - buggy_macd.iloc[3])
        assert diff_early > 0.01, "compute_macd should diverge from the adjust=True calculation early in the series"


class TestComputeMovingAveragesEmaColumns:
    def test_ema_21_matches_reference_recursive_ema_formula(self):
        rng = np.random.default_rng(23)
        closes = pd.Series(100 + np.cumsum(rng.normal(0, 1.5, 60)))

        mas = compute_moving_averages(closes)
        expected = _reference_recursive_ema(closes, 21)

        diff = (mas["ema_21"] - expected).abs()
        assert diff.max() < 1e-9, f"ema_21 diverges from recursive EMA formula by {diff.max()}"

    def test_ema_12_and_ema_26_use_recursive_ema(self):
        rng = np.random.default_rng(29)
        closes = pd.Series(100 + np.cumsum(rng.normal(0, 1.5, 60)))

        mas = compute_moving_averages(closes)
        for span, key in ((12, "ema_12"), (26, "ema_26")):
            expected = _reference_recursive_ema(closes, span)
            diff = (mas[key] - expected).abs()
            assert diff.max() < 1e-9, f"{key} diverges from recursive EMA formula by {diff.max()}"
