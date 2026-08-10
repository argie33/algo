#!/usr/bin/env python3
"""Regression test for phase7_signal_generation._compute_risk_score, found via fuzzing
with pathological inputs on 2026-08-10.

A NaN atr_14 or close silently produced risk_score=100.0 - the BEST possible score, not a
neutral or failed one - because `max(0.0, min(100.0, 100.0 - (nan * 5)))` washes NaN out
via Python's min()/max() short-circuit comparison behavior (`nan < 100.0` is False, so
min() keeps 100.0 rather than propagating NaN). This directly violates the function's own
docstring contract ("never silent 50.0 default... Either data exists or scoring halts") -
silently scoring corrupted volatility data as the LOWEST-risk stock available is worse
than a neutral default, since it actively misrepresents unknown risk and feeds directly
into which symbols Phase 7 ranks and selects for real trades.

Same bug class already found and fixed this session in position_sizer.py,
utils/validation/financial.py, phase8_entry_execution.py, exit_engine.py, and
order_manager.py.
"""

import math

import pytest

from algo.orchestrator.phase7_signal_generation import _compute_risk_score


class TestComputeRiskScoreRejectsNanAndInfinity:
    def test_nan_atr_raises_not_silently_returns_best_score(self):
        with pytest.raises(ValueError, match="ATR"):
            _compute_risk_score(float("nan"), 100.0)

    def test_nan_close_raises(self):
        with pytest.raises(ValueError, match="Close"):
            _compute_risk_score(2.0, float("nan"))

    def test_infinite_atr_raises(self):
        with pytest.raises(ValueError, match="ATR"):
            _compute_risk_score(float("inf"), 100.0)

    def test_negative_atr_raises_not_silently_scored_as_excellent(self):
        """A negative ATR is physically invalid data, not a legitimately low-risk stock -
        must not be silently scored as the best possible (100.0)."""
        with pytest.raises(ValueError, match="ATR"):
            _compute_risk_score(-2.0, 100.0)

    def test_zero_atr_still_legitimately_scores_100(self):
        """Zero volatility genuinely is the best case, unlike NaN/negative which are
        corrupted data - must not be over-rejected by the fix."""
        score = _compute_risk_score(0.0, 100.0)
        assert score == 100.0

    def test_normal_inputs_produce_finite_bounded_score(self):
        for atr, close in [(2.0, 100.0), (5.0, 50.0), (0.5, 10.0)]:
            score = _compute_risk_score(atr, close)
            assert math.isfinite(score)
            assert 0.0 <= score <= 100.0
