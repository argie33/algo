#!/usr/bin/env python3
"""Regression test for algo/orchestrator/phase7_signal_generation.py's ranking-input
validation, found via manual code audit 2026-08-10 (same NaN-comparison-guard class
fixed 40+ times elsewhere this session).

`isinstance(sqs, (int, float))` does NOT catch NaN/Infinity - `float('nan')` is a real
float instance. A NaN signal_quality_score sailing through into the downstream
`.sort(key=lambda s: float(s["signal_quality_score"]), reverse=True)` call has no total
order in Python (`NaN < x` and `x < NaN` are both False) - the NaN-scored signal's
position in the ranked list is undefined, potentially landing at the top and proceeding
toward real trade execution as if it were the highest-quality candidate.

Fixed by extracting the validation into `_validate_signal_quality_score_for_ranking()`
(same testability pattern as this file's existing `_compute_risk_score` and
`_should_halt_on_zero_scored_symbols` extractions) and adding an explicit
`math.isnan()`/`math.isinf()` check alongside the pre-existing None/type checks.
"""

import pytest

from algo.orchestrator.phase7_signal_generation import _validate_signal_quality_score_for_ranking


class TestSignalQualityScoreRankingGuard:
    def test_nan_score_raises_not_silently_ranked(self):
        with pytest.raises(ValueError, match="non-finite"):
            _validate_signal_quality_score_for_ranking(float("nan"), "AAPL")

    def test_infinite_score_raises(self):
        with pytest.raises(ValueError, match="non-finite"):
            _validate_signal_quality_score_for_ranking(float("inf"), "AAPL")

    def test_negative_infinite_score_raises(self):
        with pytest.raises(ValueError, match="non-finite"):
            _validate_signal_quality_score_for_ranking(float("-inf"), "AAPL")

    def test_none_score_raises_runtime_error(self):
        """Sanity check: the pre-existing None guard (a logic-error signal, not a data
        corruption signal) must still work and raise its own distinct error type."""
        with pytest.raises(RuntimeError, match="None signal_quality_score"):
            _validate_signal_quality_score_for_ranking(None, "AAPL")

    def test_wrong_type_score_raises_value_error(self):
        """Sanity check: the pre-existing type guard must still work."""
        with pytest.raises(ValueError, match="expected float"):
            _validate_signal_quality_score_for_ranking("not a number", "AAPL")

    def test_normal_finite_score_does_not_raise(self):
        for sqs in [0, 50, 100, 42.5, 0.0, 100.0]:
            _validate_signal_quality_score_for_ranking(sqs, "AAPL")  # must not raise
