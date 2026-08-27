#!/usr/bin/env python3
"""Regression test for algo/orchestrator/phase7_signal_generation.py's ranking-input
validation.

Originally written 2026-08-10 against signal_quality_score (found via manual code audit,
same NaN-comparison-guard class fixed 40+ times elsewhere that session). Retargeted
2026-08-27 when Phase 7's ranking key was switched back to composite_score (real-money-
readiness review - live data showed signal_quality_score has no/inverse predictive power
for forward returns; see phase7_signal_generation.py's module docstring for the full
history) - the underlying NaN-safety property being tested is identical, only the field
name changed along with the renamed `_validate_composite_score_for_ranking()` function.

`isinstance(score, (int, float))` does NOT catch NaN/Infinity - `float('nan')` is a real
float instance. A NaN composite_score sailing through into the downstream
`.sort(key=lambda s: float(s["composite_score"]), reverse=True)` call has no total
order in Python (`NaN < x` and `x < NaN` are both False) - the NaN-scored signal's
position in the ranked list is undefined, potentially landing at the top and proceeding
toward real trade execution as if it were the highest-quality candidate.
"""

import pytest

from algo.orchestrator.phase7_signal_generation import _validate_composite_score_for_ranking


class TestCompositeScoreRankingGuard:
    def test_nan_score_raises_not_silently_ranked(self):
        with pytest.raises(ValueError, match="non-finite"):
            _validate_composite_score_for_ranking(float("nan"), "AAPL")

    def test_infinite_score_raises(self):
        with pytest.raises(ValueError, match="non-finite"):
            _validate_composite_score_for_ranking(float("inf"), "AAPL")

    def test_negative_infinite_score_raises(self):
        with pytest.raises(ValueError, match="non-finite"):
            _validate_composite_score_for_ranking(float("-inf"), "AAPL")

    def test_none_score_raises_runtime_error(self):
        """Sanity check: the pre-existing None guard (a logic-error signal, not a data
        corruption signal) must still work and raise its own distinct error type."""
        with pytest.raises(RuntimeError, match="None composite_score"):
            _validate_composite_score_for_ranking(None, "AAPL")

    def test_wrong_type_score_raises_value_error(self):
        """Sanity check: the pre-existing type guard must still work."""
        with pytest.raises(ValueError, match="expected float"):
            _validate_composite_score_for_ranking("not a number", "AAPL")

    def test_normal_finite_score_does_not_raise(self):
        for score in [0, 50, 100, 42.5, 0.0, 100.0]:
            _validate_composite_score_for_ranking(score, "AAPL")  # must not raise
