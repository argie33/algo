#!/usr/bin/env python3
"""Regression test for RiskMetricsLoader._calculate_volatility using Barra USE4's real
EWMA-weighted (42-trading-day half-life) DASTD construction, REPLACING the equal-weighted
sample-variance (N-1, Bessel's correction) calculation this file used to lock in (factor-purity
sweep follow-up, 2026-09-17 - see _calculate_volatility's own docstring for the full citation:
Barra US Equity Model USE4 Methodology Notes, Volatility descriptor). An equal-weighted window
treats a 41-day-old return identically to yesterday's; the real descriptor deliberately weights
recent observations more heavily via exponential decay.
"""

import math
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np

from loaders.load_risk_metrics_daily import DASTD_DECAY_FACTOR, RiskMetricsLoader


def _reference_ewma_volatility(returns: list[float]) -> float:
    """Independent reference implementation of the same EWMA construction
    _calculate_volatility implements, written directly against numpy rather than copying that
    method's own arithmetic, so this test can't pass merely by mirroring a shared bug."""
    n = len(returns)
    weights = np.array([DASTD_DECAY_FACTOR ** (n - 1 - i) for i in range(n)])
    weights = weights / weights.sum()
    weighted_mean = np.average(returns, weights=weights)
    weighted_variance = np.average((np.asarray(returns) - weighted_mean) ** 2, weights=weights)
    return float(math.sqrt(weighted_variance) * math.sqrt(252))


def _patch_now(as_of: date):
    """Pin `datetime.now(EASTERN_TZ)` to `as_of` so the 2026-09-01 stale-price gate (see
    STALE_PRICE_TRADING_DAYS_THRESHOLD in loaders/load_risk_metrics_daily.py) doesn't fire
    against these tests' synthetic historical `today` - this file is testing the sample-size/
    zero-volatility guards, not staleness."""
    return patch(
        "loaders.load_risk_metrics_daily.datetime",
        **{"now.return_value": datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc)},
    )


class TestCalculateVolatilityUsesEwmaWeighting:
    def test_matches_independent_ewma_reference(self):
        rng = np.random.default_rng(17)
        returns = list(rng.normal(0, 0.02, 30))

        actual = RiskMetricsLoader._calculate_volatility(returns)
        expected = _reference_ewma_volatility(returns)

        assert actual is not None
        assert abs(actual - expected) < 1e-9, f"expected {expected}, got {actual}"

    def test_does_not_match_equal_weighted_sample_variance(self):
        """Regression guard: equal-weighted sample variance (every return weighted
        identically regardless of recency) is the OLD, now-replaced construction - if
        reintroduced, this test fails."""
        rng = np.random.default_rng(3)
        returns = list(rng.normal(0, 0.02, 30))

        actual = RiskMetricsLoader._calculate_volatility(returns)
        equal_weighted_result = float(np.std(returns, ddof=1) * math.sqrt(252))

        assert actual is not None
        assert abs(actual - equal_weighted_result) > 1e-4, (
            "compute_volatility should diverge from the equal-weighted sample-variance calculation"
        )

    def test_recent_return_weighted_more_than_old_return(self):
        """The whole point of EWMA weighting: a large move placed at the RECENT end of the
        window must move annualized volatility more than the identical move placed at the
        OLD end - an equal-weighted calculation would score both placements identically."""
        base = [0.001] * 29
        recent_shock = [*base, 0.05]
        old_shock = [0.05, *base]

        vol_recent_shock = RiskMetricsLoader._calculate_volatility(recent_shock)
        vol_old_shock = RiskMetricsLoader._calculate_volatility(old_shock)

        assert vol_recent_shock is not None and vol_old_shock is not None
        assert vol_recent_shock > vol_old_shock

    def test_two_return_minimum_matches_ewma_reference(self):
        """At the minimum viable sample size (2 returns), verify against the same
        independent reference implementation used above."""
        returns = [0.01, -0.01]
        actual = RiskMetricsLoader._calculate_volatility(returns)
        expected = _reference_ewma_volatility(returns)
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
    in load_stock_scores.py._score_risk - the single highest weight of any risk
    sub-component (more than volatility_60d's 0.20 or volatility_30d's 0.15). It previously
    only required len(returns) >= 2 (a divide-by-zero guard borrowed from
    _calculate_volatility, not a real sample-size floor), so a stock with a handful of days
    of price history got a "252-day" figure confidently reported and given the most
    influence over its stability score."""

    def _rows(self, n: int, today: date) -> list[tuple[date, float, float]]:
        # 3-tuple (date, close, adj_close) matching the SELECT date, close, adj_close shape
        # _compute_stability_row now queries (2026-09-01 adj_close fix) - adj_close equals
        # close here since these synthetic rows have no real corporate action to adjust for.
        return [(today - timedelta(days=i), 100.0 + (i % 7), 100.0 + (i % 7)) for i in range(n)]

    def test_small_sample_leaves_volatility_252d_unavailable(self):
        today = date(2026, 7, 20)
        # 10 days of history (9 returns) clears the >=5-row early gate but is far short
        # of a meaningful long-window sample.
        rows = self._rows(10, today)
        spy_rows = self._rows(10, today)

        loader = RiskMetricsLoader()
        with (
            patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows, spy_rows)),
            _patch_now(today),
        ):
            result = loader._compute_stability_row("NEWIPO")

        assert result["volatility_252d"] is None
        assert result["volatility_252d_unavailable_reason"] == "insufficient_history"

    def test_large_sample_still_populates_volatility_252d(self):
        today = date(2026, 7, 20)
        rows = self._rows(100, today)
        spy_rows = self._rows(100, today)

        loader = RiskMetricsLoader()
        with (
            patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows, spy_rows)),
            _patch_now(today),
        ):
            result = loader._compute_stability_row("ESTABLISHED")

        assert result["volatility_252d"] is not None


class TestZeroVolatilityIsPreservedNotDiscarded:
    """A stock with an unchanged closing price for its entire lookback window (illiquid/
    thinly-traded tickers, or a halted symbol carrying a stale last price) computes a
    genuine volatility of exactly 0.0. `if vol_Nd else None` treats 0.0 as falsy and
    silently discards it as "unavailable" - load_stock_scores.py._score_risk checks
    `is not None` to decide whether to include each component, so this dropped a real,
    meaningful "very low volatility" reading from the risk score entirely."""

    def _flat_rows(self, n: int, today: date, price: float = 100.0) -> list[tuple[date, float, float]]:
        return [(today - timedelta(days=i), price, price) for i in range(n)]

    def test_flat_price_stock_reports_zero_not_none(self):
        today = date(2026, 7, 20)
        rows = self._flat_rows(100, today)
        spy_rows = self._flat_rows(100, today, price=400.0)

        loader = RiskMetricsLoader()
        with (
            patch("loaders.load_risk_metrics_daily.DatabaseContext", return_value=_db_context_mock(rows, spy_rows)),
            _patch_now(today),
        ):
            result = loader._compute_stability_row("FLATLINE")

        assert result["volatility_30d"] == 0.0
        assert result["volatility_60d"] == 0.0
        assert result["volatility_252d"] == 0.0
        assert result["volatility_30d_unavailable_reason"] is None
        assert result["volatility_60d_unavailable_reason"] is None
        assert result["volatility_252d_unavailable_reason"] is None
        assert result["data_unavailable"] is False
