#!/usr/bin/env python3
"""Regression test for RiskMetricsLoader._calculate_amihud_illiquidity - the Amihud (2002)
illiquidity measure (mean(|daily return| / dollar volume)), computed and stored but not yet
wired into any scoring pillar's weight (see risk_scoring.py's own module docstring: flagged
as an OPEN QUESTION 2026-08-25, verified with real forward-return evidence in this repo's own
data, t=3.34, but never implemented until this pass - a genuine new computation, unlike Size).
"""

from loaders.load_risk_metrics_daily import RiskMetricsLoader


class TestCalculateAmihudIlliquidity:
    def test_matches_hand_computed_reference(self):
        returns = [0.01, -0.02, 0.005]
        dollar_volumes = [1_000_000.0, 2_000_000.0, 500_000.0]

        expected = (abs(0.01) / 1_000_000.0 + abs(-0.02) / 2_000_000.0 + abs(0.005) / 500_000.0) / 3

        actual = RiskMetricsLoader._calculate_amihud_illiquidity(returns, dollar_volumes)

        assert actual is not None
        assert abs(actual - expected) < 1e-15

    def test_higher_illiquidity_for_thinner_dollar_volume(self):
        """The whole point of the measure: the SAME return magnitude on THINNER dollar
        volume must score as MORE illiquid (a higher Amihud value)."""
        returns = [0.01] * 10
        thin_volumes = [10_000.0] * 10
        deep_volumes = [10_000_000.0] * 10

        thin = RiskMetricsLoader._calculate_amihud_illiquidity(returns, thin_volumes)
        deep = RiskMetricsLoader._calculate_amihud_illiquidity(returns, deep_volumes)

        assert thin is not None and deep is not None
        assert thin > deep

    def test_zero_or_missing_dollar_volume_days_are_skipped_not_treated_as_infinite(self):
        """A day with unknown/zero dollar volume must be excluded, not fabricated as an
        extreme illiquidity reading - same governance principle as this pillar's other
        min-weight-available guards (skip what's unavailable, never invent a fallback)."""
        returns = [0.01, 0.02, 0.03]
        dollar_volumes = [1_000_000.0, 0.0, 500_000.0]

        actual = RiskMetricsLoader._calculate_amihud_illiquidity(returns, dollar_volumes)
        expected_using_only_valid_days = (abs(0.01) / 1_000_000.0 + abs(0.03) / 500_000.0) / 2

        assert actual is not None
        assert abs(actual - expected_using_only_valid_days) < 1e-15

    def test_mismatched_lengths_returns_none(self):
        assert RiskMetricsLoader._calculate_amihud_illiquidity([0.01, 0.02], [1_000_000.0]) is None

    def test_insufficient_valid_days_returns_none(self):
        assert RiskMetricsLoader._calculate_amihud_illiquidity([], []) is None
        assert RiskMetricsLoader._calculate_amihud_illiquidity([0.01], [1_000_000.0]) is None
        # Only one valid (non-zero-volume) day survives filtering - still below the floor.
        assert RiskMetricsLoader._calculate_amihud_illiquidity([0.01, 0.02], [1_000_000.0, 0.0]) is None
