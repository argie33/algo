#!/usr/bin/env python3
"""Regression test for RiskMetricsLoader._calculate_volatility using sample variance
(N-1, Bessel's correction) rather than population variance (N) - consistent with this
same loader's beta calculation (_get_beta_from_db uses np.var(..., ddof=1)/np.cov(), both
sample-variance conventions). Population variance systematically understates volatility.
"""

import math

import numpy as np

from loaders.load_risk_metrics_daily import RiskMetricsLoader


class TestCalculateVolatilityUsesSampleVariance:
    def test_matches_numpy_ddof_1_reference(self):
        rng = np.random.default_rng(17)
        returns = list(rng.normal(0, 0.02, 30))

        actual = RiskMetricsLoader._calculate_volatility(returns)
        expected = float(np.std(returns, ddof=1) * math.sqrt(252))

        assert actual is not None
        assert abs(actual - expected) < 1e-9, f"expected {expected}, got {actual}"

    def test_does_not_match_population_variance_ddof_0(self):
        """Regression guard: population variance (ddof=0, dividing by N) is a
        systematically different, lower number - if reintroduced, this test fails."""
        rng = np.random.default_rng(3)
        returns = list(rng.normal(0, 0.02, 30))

        actual = RiskMetricsLoader._calculate_volatility(returns)
        population_variance_result = float(np.std(returns, ddof=0) * math.sqrt(252))

        assert actual is not None
        assert abs(actual - population_variance_result) > 1e-4, (
            "compute_volatility should diverge from the population-variance (ddof=0) calculation"
        )
        # Sample variance (N-1) is always >= population variance (N) for the same data
        assert actual > population_variance_result

    def test_two_return_minimum_matches_sample_variance_not_population(self):
        """At the minimum viable sample size (2 returns), N vs N-1 diverges the most
        (~41% relative difference) - the sharpest possible regression signal."""
        returns = [0.01, -0.01]
        actual = RiskMetricsLoader._calculate_volatility(returns)
        expected = float(np.std(returns, ddof=1) * math.sqrt(252))
        assert actual is not None
        assert abs(actual - expected) < 1e-9

    def test_insufficient_data_returns_none(self):
        assert RiskMetricsLoader._calculate_volatility([]) is None
        assert RiskMetricsLoader._calculate_volatility([0.01]) is None
