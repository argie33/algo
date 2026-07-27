#!/usr/bin/env python3
"""Regression test for RiskMetricsLoader._calculate_volatility using sample variance
(N-1, Bessel's correction) rather than population variance (N) - consistent with this
same loader's beta calculation (_get_beta_from_db uses np.var(..., ddof=1)/np.cov(), both
sample-variance conventions). Population variance systematically understates volatility.
"""

import math
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

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


def _db_context_mock(price_rows, spy_rows, debt_to_assets=None):
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = (debt_to_assets,) if debt_to_assets is not None else None
    mock_cur.fetchall.side_effect = [price_rows, spy_rows]
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    return mock_ctx


class TestVolatility252dRequiresMeaningfulSample:
    """volatility_252d is scored as "12-month annualized volatility" and given 0.40 weight
    in load_stock_scores.py._score_stability - the single highest weight of any stability
    sub-component (more than volatility_60d's 0.20 or volatility_30d's 0.15). It previously
    only required len(returns) >= 2 (a divide-by-zero guard borrowed from
    _calculate_volatility, not a real sample-size floor), so a stock with a handful of days
    of price history got a "252-day" figure confidently reported and given the most
    influence over its stability score."""

    def _rows(self, n: int, today: date) -> list[tuple[date, float]]:
        return [(today - timedelta(days=i), 100.0 + (i % 7)) for i in range(n)]

    def test_small_sample_leaves_volatility_252d_unavailable(self):
        today = date(2026, 7, 20)
        # 10 days of history (9 returns) clears the >=5-row early gate but is far short
        # of a meaningful long-window sample.
        rows = self._rows(10, today)
        spy_rows = self._rows(10, today)

        loader = RiskMetricsLoader()
        with patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows, spy_rows)):
            result = loader._compute_stability_row("NEWIPO")

        assert result["volatility_252d"] is None
        assert result["volatility_252d_unavailable_reason"] == "insufficient_history"

    def test_large_sample_still_populates_volatility_252d(self):
        today = date(2026, 7, 20)
        rows = self._rows(100, today)
        spy_rows = self._rows(100, today)

        loader = RiskMetricsLoader()
        with patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows, spy_rows)):
            result = loader._compute_stability_row("ESTABLISHED")

        assert result["volatility_252d"] is not None
