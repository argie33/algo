#!/usr/bin/env python3
"""Regression test for loaders/load_positioning_metrics.py's
_compute_short_interest_pct_change() (renamed 2026-08-17, migration 1203, from
_compute_short_interest_trend() - now returns the continuous % change instead of a
3-value text enum; see this file's prior name for the original NaN-guard bug writeup).

The original inline guard used `prior_pct != 0` to avoid division by zero - `!=` is TRUE
for NaN against everything including 0, so a NaN prior_pct sailed past that "protection"
into a real division, producing a NaN relative_change. That NaN then failed both the
`> 0.05` and `< -0.05` comparisons (both False for NaN) and fell through to the else
branch, silently mislabeling corrupted/unavailable short-interest data as "stable" instead
of leaving the value unset (which the caller correctly surfaces as
short_interest_pct_change_unavailable_reason="insufficient_history"). The guard is
unchanged by the rename, so this coverage still applies.
"""

import math

from loaders.load_positioning_metrics import _compute_short_interest_pct_change


class TestShortInterestPctChangeNanGuard:
    def test_nan_prior_pct_returns_none(self) -> None:
        assert _compute_short_interest_pct_change(5.0, float("nan")) is None

    def test_nan_current_pct_returns_none(self) -> None:
        assert _compute_short_interest_pct_change(float("nan"), 5.0) is None

    def test_infinite_prior_pct_returns_none(self) -> None:
        assert _compute_short_interest_pct_change(5.0, float("inf")) is None

    def test_none_inputs_return_none(self) -> None:
        assert _compute_short_interest_pct_change(None, 5.0) is None
        assert _compute_short_interest_pct_change(5.0, None) is None

    def test_genuinely_zero_prior_pct_returns_none_not_a_crash(self) -> None:
        """Sanity check: the fix must still avoid a real ZeroDivisionError."""
        assert _compute_short_interest_pct_change(5.0, 0.0) is None

    def test_normal_increasing_change_is_positive(self) -> None:
        assert _compute_short_interest_pct_change(11.0, 10.0) == 10.0

    def test_normal_decreasing_change_is_negative(self) -> None:
        assert _compute_short_interest_pct_change(8.0, 10.0) == -20.0

    def test_small_change_is_near_zero(self) -> None:
        result = _compute_short_interest_pct_change(10.2, 10.0)
        assert result is not None
        assert 0.0 < result < 5.0

    def test_result_is_finite_for_all_normal_inputs(self) -> None:
        for current, prior in [(1.0, 1.0), (50.0, 25.0), (0.01, 0.02)]:
            result = _compute_short_interest_pct_change(current, prior)
            assert result is not None
            assert math.isfinite(result)
