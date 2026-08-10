#!/usr/bin/env python3
"""Regression test for loaders/load_positioning_metrics.py's
_compute_short_interest_trend(), found via a repo-wide second-pass audit for the
inverted-guard NaN bug variant (same class as
phase9_reconciliation.py's _repair_missing_exit_prices() fix this session).

The original inline guard used `prior_pct != 0` to avoid division by zero - `!=` is TRUE
for NaN against everything including 0, so a NaN prior_pct sailed past that "protection"
into a real division, producing a NaN relative_change. That NaN then failed both the
`> 0.05` and `< -0.05` comparisons (both False for NaN) and fell through to the else
branch, silently mislabeling corrupted/unavailable short-interest data as "stable" instead
of leaving the trend unset (which the caller correctly surfaces as
short_interest_trend_unavailable_reason="insufficient_history").
"""

import math

from loaders.load_positioning_metrics import _compute_short_interest_trend


class TestShortInterestTrendNanGuard:
    def test_nan_prior_pct_returns_none_not_stable(self) -> None:
        assert _compute_short_interest_trend(5.0, float("nan")) is None

    def test_nan_current_pct_returns_none(self) -> None:
        assert _compute_short_interest_trend(float("nan"), 5.0) is None

    def test_infinite_prior_pct_returns_none(self) -> None:
        assert _compute_short_interest_trend(5.0, float("inf")) is None

    def test_none_inputs_return_none(self) -> None:
        assert _compute_short_interest_trend(None, 5.0) is None
        assert _compute_short_interest_trend(5.0, None) is None

    def test_genuinely_zero_prior_pct_returns_none_not_a_crash(self) -> None:
        """Sanity check: the fix must still avoid a real ZeroDivisionError."""
        assert _compute_short_interest_trend(5.0, 0.0) is None

    def test_normal_increasing_trend(self) -> None:
        assert _compute_short_interest_trend(11.0, 10.0) == "increasing"

    def test_normal_decreasing_trend(self) -> None:
        assert _compute_short_interest_trend(8.0, 10.0) == "decreasing"

    def test_normal_stable_trend(self) -> None:
        assert _compute_short_interest_trend(10.2, 10.0) == "stable"

    def test_result_is_finite_and_bounded_for_all_normal_inputs(self) -> None:
        for current, prior in [(1.0, 1.0), (50.0, 25.0), (0.01, 0.02)]:
            result = _compute_short_interest_trend(current, prior)
            assert result in ("increasing", "decreasing", "stable")
            assert not (isinstance(result, float) and math.isnan(result))
