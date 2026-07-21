#!/usr/bin/env python3
"""Regression test for loaders/load_trend_analysis.py::_compute_scores_vectorized.

Guards against minervini_trend_score silently treating missing close/sma50/sma200 data
as "criterion failed" (0 points) instead of "undetermined" (NaN score). A stock without
200 days of price history (sma200 is NaN, e.g. a recent IPO) previously had c1/c3/c7
silently score 0 - pandas comparisons against NaN evaluate to False, not NaN - understating
the score by up to 3/8 points instead of correctly marking it unavailable.
"""

import numpy as np
import pandas as pd

from loaders.load_trend_analysis import _compute_scores_vectorized


def _build_frame(**overrides):
    base = {
        "close": pd.Series([100.0]),
        "sma_50": pd.Series([95.0]),
        "sma_200": pd.Series([90.0]),
        "roc_20d": pd.Series([2.0]),
        "roc_60d": pd.Series([5.0]),
        "roc_252d": pd.Series([15.0]),
        "rsi_14": pd.Series([60.0]),
    }
    base.update(overrides)
    return pd.DataFrame(base)


class TestMinerviniScoreMissingDataHandling:
    def test_complete_data_produces_real_score(self):
        merged = _build_frame()
        result = _compute_scores_vectorized(merged)
        assert result["minervini_trend_score"].iloc[0] == 8.0

    def test_missing_sma200_produces_nan_score_not_deflated_score(self):
        merged = _build_frame(sma_200=pd.Series([np.nan]))
        result = _compute_scores_vectorized(merged)
        assert pd.isna(result["minervini_trend_score"].iloc[0])

    def test_missing_close_produces_nan_score(self):
        merged = _build_frame(close=pd.Series([np.nan]))
        result = _compute_scores_vectorized(merged)
        assert pd.isna(result["minervini_trend_score"].iloc[0])

    def test_missing_sma50_produces_nan_score(self):
        merged = _build_frame(sma_50=pd.Series([np.nan]))
        result = _compute_scores_vectorized(merged)
        assert pd.isna(result["minervini_trend_score"].iloc[0])

    def test_missing_roc_still_produces_nan_score(self):
        # Confirms the fix didn't regress the already-correct c4/c5/c6/c8 NaN handling
        merged = _build_frame(roc_60d=pd.Series([np.nan]))
        result = _compute_scores_vectorized(merged)
        assert pd.isna(result["minervini_trend_score"].iloc[0])

    def test_weinstein_stage_consistent_with_minervini_on_missing_sma(self):
        # Both should treat the same missing-SMA condition as "unavailable", not just one of them
        merged = _build_frame(sma_200=pd.Series([np.nan]))
        result = _compute_scores_vectorized(merged)
        assert pd.isna(result["minervini_trend_score"].iloc[0])
        assert pd.isna(result["weinstein_stage"].iloc[0])
