"""Regression tests for utils/external/yfinance_analyst_ratings.py.

Covers fetch_analyst_actions()'s DataFrame-to-row-dict conversion: valid action mapping,
firm-missing rows dropped (firm is part of the uniqueness key), lookback filtering, no-coverage
symbols returning None (not an error), and rate-limit errors correctly reported to the shared
circuit breaker.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from utils.external.yfinance_analyst_ratings import fetch_analyst_actions, fetch_forward_growth_estimates


def _mock_ticker_with_df(df):
    mock_ticker = MagicMock()
    mock_ticker.upgrades_downgrades = df
    return mock_ticker


@pytest.fixture(autouse=True)
def _patch_circuit_breaker():
    with (
        patch("utils.external.yfinance_analyst_ratings.get_circuit_breaker") as mock_get_cb,
        patch("utils.loaders.retry_helper.time.sleep"),
    ):
        cb = MagicMock()
        mock_get_cb.return_value = cb
        yield cb


class TestFetchAnalystActions:
    def test_maps_real_rows_to_expected_schema(self, _patch_circuit_breaker):
        today = datetime.now(timezone.utc).date()
        df = pd.DataFrame(
            {
                "Firm": ["Morgan Stanley", "Goldman Sachs"],
                "ToGrade": ["Overweight", "Buy"],
                "FromGrade": ["Equal-Weight", "Hold"],
                "Action": ["up", "up"],
            },
            index=pd.to_datetime([today.isoformat(), today.isoformat()]),
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(df)):
            rows = fetch_analyst_actions("AAPL")

        assert rows is not None
        assert len(rows) == 2
        assert rows[0]["symbol"] == "AAPL"
        assert rows[0]["firm"] == "Morgan Stanley"
        assert rows[0]["action"] == "up"
        assert rows[0]["old_rating"] == "Equal-Weight"
        assert rows[0]["new_rating"] == "Overweight"
        assert isinstance(rows[0]["action_date"], date)

    def test_no_coverage_returns_none_not_error(self, _patch_circuit_breaker):
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(None)):
            assert fetch_analyst_actions("ZZZZ") is None

        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(pd.DataFrame())):
            assert fetch_analyst_actions("ZZZZ") is None

    def test_rows_with_missing_firm_are_dropped(self, _patch_circuit_breaker):
        today = datetime.now(timezone.utc).date()
        df = pd.DataFrame(
            {"Firm": [None], "ToGrade": ["Buy"], "FromGrade": ["Hold"], "Action": ["up"]},
            index=pd.to_datetime([today.isoformat()]),
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(df)):
            assert fetch_analyst_actions("AAPL") is None

    def test_actions_older_than_lookback_are_excluded(self, _patch_circuit_breaker):
        old_date = datetime.now(timezone.utc).date() - timedelta(days=800)
        df = pd.DataFrame(
            {"Firm": ["Old Firm"], "ToGrade": ["Buy"], "FromGrade": ["Hold"], "Action": ["up"]},
            index=pd.to_datetime([old_date.isoformat()]),
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(df)):
            assert fetch_analyst_actions("AAPL", lookback_days=730) is None

    def test_unrecognized_action_value_maps_to_none_not_dropped(self, _patch_circuit_breaker):
        today = datetime.now(timezone.utc).date()
        df = pd.DataFrame(
            {"Firm": ["Some Firm"], "ToGrade": ["Buy"], "FromGrade": ["Hold"], "Action": ["weird_new_value"]},
            index=pd.to_datetime([today.isoformat()]),
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(df)):
            rows = fetch_analyst_actions("AAPL")
        assert rows is not None
        assert rows[0]["action"] is None

    def test_fetch_failure_raises_and_reports_rate_limit(self, _patch_circuit_breaker):
        """FIXED 2026-08-19 (goal: "no SEC data" audit): a persistent rate-limit-shaped
        failure now gets one retry (see _fetch_with_circuit_breaker's own comment) before
        giving up, so a real, still-failing rate limit reports twice - once per attempt,
        each of which independently observes and reports the same rate-limit error."""
        with patch("yfinance.Ticker", side_effect=RuntimeError("Invalid Crumb (401)")):
            with pytest.raises(RuntimeError, match="upgrades_downgrades fetch failed"):
                fetch_analyst_actions("AAPL")
        assert _patch_circuit_breaker.report_rate_limit_error.call_count == 2

    def test_fetch_failure_non_rate_limit_does_not_report_rate_limit(self, _patch_circuit_breaker):
        with patch("yfinance.Ticker", side_effect=ValueError("unexpected parse error")):
            with pytest.raises(RuntimeError, match="upgrades_downgrades fetch failed"):
                fetch_analyst_actions("AAPL")
        _patch_circuit_breaker.report_rate_limit_error.assert_not_called()

    def test_success_reports_success_to_circuit_breaker(self, _patch_circuit_breaker):
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(None)):
            fetch_analyst_actions("AAPL")
        _patch_circuit_breaker.report_success.assert_called_once()

    def test_transient_failure_recovers_on_retry(self, _patch_circuit_breaker):
        """FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit): a single
        failed attempt used to propagate straight up as a permanent-looking RuntimeError,
        indistinguishable to load_analyst_upgrade_downgrade.py's caller from genuine "no
        coverage" - live-confirmed NVDA/MSFT/TSM/GOOGL (hundreds of real analyst rows each,
        all resolve fine on a fresh unretried call moments later) still carrying a stale
        "no_analyst_coverage" marker because a same-day run's single attempt hit a
        transient hiccup with zero retry anywhere in the chain. One retry must give a
        transient failure a real chance to recover within the same call."""
        today = datetime.now(timezone.utc).date()
        df = pd.DataFrame(
            {"Firm": ["Morgan Stanley"], "ToGrade": ["Buy"], "FromGrade": ["Hold"], "Action": ["up"]},
            index=pd.to_datetime([today.isoformat()]),
        )
        with patch(
            "yfinance.Ticker",
            side_effect=[TimeoutError("socket timeout"), _mock_ticker_with_df(df)],
        ):
            rows = fetch_analyst_actions("NVDA")

        assert rows is not None
        assert len(rows) == 1
        assert rows[0]["firm"] == "Morgan Stanley"
        # The circuit breaker must be re-checked on the retry, not just the first attempt.
        assert _patch_circuit_breaker.wait_or_raise.call_count == 2


def _mock_ticker_with_estimates(earnings_df=None, revenue_df=None, eps_trend_df=None):
    mock_ticker = MagicMock()
    mock_ticker.earnings_estimate = earnings_df
    mock_ticker.revenue_estimate = revenue_df
    mock_ticker.eps_trend = eps_trend_df
    return mock_ticker


class TestFetchForwardGrowthEstimates:
    """Regression tests for fetch_forward_growth_estimates() - added 2026-08-28 (goal:
    Growth-pillar-audit session, user directive to capture real forward-looking data
    yfinance already exposes on Ticker.earnings_estimate/revenue_estimate/eps_trend that
    this repo wasn't pulling before)."""

    def test_all_three_endpoints_populated(self, _patch_circuit_breaker):
        earnings_df = pd.DataFrame(
            {"avg": [1.98, 8.81, 9.53], "growth": [0.0242, 0.1813, 0.0816]},
            index=["+1q", "0y", "+1y"],
        )
        revenue_df = pd.DataFrame({"avg": [1.1e11], "growth": [0.0991]}, index=["+1y"])
        eps_trend_df = pd.DataFrame(
            {"current": [8.81249], "90daysAgo": [8.75324]},
            index=["0y"],
        )
        with patch(
            "yfinance.Ticker",
            return_value=_mock_ticker_with_estimates(earnings_df, revenue_df, eps_trend_df),
        ):
            result = fetch_forward_growth_estimates("AAPL")

        assert result is not None
        assert result["forward_eps_growth_current_fy"] == pytest.approx(0.1813)
        assert result["forward_eps_growth_next_fy"] == pytest.approx(0.0816)
        assert result["forward_revenue_growth_next_fy"] == pytest.approx(0.0991)
        # (8.81249 - 8.75324) / |8.75324| * 100
        assert result["eps_estimate_revision_90d_pct"] == pytest.approx(0.6769, abs=1e-3)

    def test_no_coverage_on_any_endpoint_returns_none(self, _patch_circuit_breaker):
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_estimates(None, None, None)):
            assert fetch_forward_growth_estimates("ZZZZ") is None

        with patch(
            "yfinance.Ticker",
            return_value=_mock_ticker_with_estimates(pd.DataFrame(), pd.DataFrame(), pd.DataFrame()),
        ):
            assert fetch_forward_growth_estimates("ZZZZ") is None

    def test_partial_coverage_returns_whatever_is_available(self, _patch_circuit_breaker):
        """revenue_estimate/eps_trend missing but earnings_estimate present - a real,
        common partial-coverage shape, not an error. The 2 unavailable fields must be
        None, not silently dropped from the result dict."""
        earnings_df = pd.DataFrame({"avg": [8.81, 9.53], "growth": [0.1813, 0.0816]}, index=["0y", "+1y"])
        with patch(
            "yfinance.Ticker",
            return_value=_mock_ticker_with_estimates(earnings_df, None, None),
        ):
            result = fetch_forward_growth_estimates("AAPL")

        assert result is not None
        assert result["forward_eps_growth_current_fy"] == pytest.approx(0.1813)
        assert result["forward_eps_growth_next_fy"] == pytest.approx(0.0816)
        assert result["forward_revenue_growth_next_fy"] is None
        assert result["eps_estimate_revision_90d_pct"] is None

    def test_zero_prior_estimate_does_not_divide_by_zero(self, _patch_circuit_breaker):
        eps_trend_df = pd.DataFrame({"current": [0.05], "90daysAgo": [0.0]}, index=["0y"])
        with patch(
            "yfinance.Ticker",
            return_value=_mock_ticker_with_estimates(None, None, eps_trend_df),
        ):
            result = fetch_forward_growth_estimates("AAPL")
        assert result is None  # the only populated field is guarded off, so no_coverage
