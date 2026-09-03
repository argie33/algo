"""Regression tests for utils/external/yfinance_analyst_ratings.py.

Covers fetch_analyst_actions()'s DataFrame-to-row-dict conversion: valid action mapping,
firm-missing rows dropped (firm is part of the uniqueness key), lookback filtering, no-coverage
symbols returning None (not an error), and rate-limit errors correctly reported to the shared
circuit breaker.

2026-08-29: the yfinance fetch itself moved from an in-process `yf.Ticker` call to
`_YfinanceAttrProcessWorker` (a persistent subprocess) - see that class's docstring and
`_fetch_with_circuit_breaker` for why. Tests below mock `_get_module_worker()` instead of
`yfinance.Ticker` - a real yf.Ticker call now happens inside a separate OS process the test
process can't patch into.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from utils.external.yfinance_analyst_ratings import fetch_analyst_actions, fetch_forward_growth_estimates

_WORKER_PATCH_TARGET = "utils.external.yfinance_analyst_ratings._get_module_worker"


def _mock_worker_for(**attr_values: object) -> MagicMock:
    """Build a mock worker whose fetch(symbol, attr, **kw) returns attr_values[attr] -
    mirrors what `getattr(yf.Ticker(symbol), attr)` used to return directly."""
    worker = MagicMock()
    worker.fetch.side_effect = lambda symbol, attr, **kw: attr_values[attr]
    return worker


def _failing_worker(exc: BaseException) -> MagicMock:
    """A mock worker whose fetch() always raises exc - mirrors a Ticker call that used to
    raise directly."""
    worker = MagicMock()
    worker.fetch.side_effect = exc
    return worker


def _mock_ticker_with_df(df):
    return _mock_worker_for(upgrades_downgrades=df)


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
        with patch(_WORKER_PATCH_TARGET, return_value=_mock_ticker_with_df(df)):
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
        with patch(_WORKER_PATCH_TARGET, return_value=_mock_ticker_with_df(None)):
            assert fetch_analyst_actions("ZZZZ") is None

        with patch(_WORKER_PATCH_TARGET, return_value=_mock_ticker_with_df(pd.DataFrame())):
            assert fetch_analyst_actions("ZZZZ") is None

    def test_rows_with_missing_firm_are_dropped(self, _patch_circuit_breaker):
        today = datetime.now(timezone.utc).date()
        df = pd.DataFrame(
            {"Firm": [None], "ToGrade": ["Buy"], "FromGrade": ["Hold"], "Action": ["up"]},
            index=pd.to_datetime([today.isoformat()]),
        )
        with patch(_WORKER_PATCH_TARGET, return_value=_mock_ticker_with_df(df)):
            assert fetch_analyst_actions("AAPL") is None

    def test_old_actions_are_kept_not_treated_as_no_coverage(self, _patch_circuit_breaker):
        """FIXED 2026-09-03: a >2-year-old real row used to be silently discarded, and
        None returned (indistinguishable from "never covered"). Live-confirmed this broke
        real mega-caps (MUFG, Santander) whose yfinance-tracked ADR rating history is real
        but not recent - see fetch_analyst_actions's own fix docstring. The consumer
        (_analyst_score) already applies its own 90-day recency window at read time, so
        this fetch-time cutoff had no scoring benefit and only destroyed real data."""
        old_date = datetime.now(timezone.utc).date() - timedelta(days=800)
        df = pd.DataFrame(
            {"Firm": ["Old Firm"], "ToGrade": ["Buy"], "FromGrade": ["Hold"], "Action": ["up"]},
            index=pd.to_datetime([old_date.isoformat()]),
        )
        with patch(_WORKER_PATCH_TARGET, return_value=_mock_ticker_with_df(df)):
            rows = fetch_analyst_actions("AAPL")
        assert rows is not None
        assert len(rows) == 1
        assert rows[0]["firm"] == "Old Firm"
        assert rows[0]["action_date"] == old_date

    def test_unrecognized_action_value_maps_to_none_not_dropped(self, _patch_circuit_breaker):
        today = datetime.now(timezone.utc).date()
        df = pd.DataFrame(
            {"Firm": ["Some Firm"], "ToGrade": ["Buy"], "FromGrade": ["Hold"], "Action": ["weird_new_value"]},
            index=pd.to_datetime([today.isoformat()]),
        )
        with patch(_WORKER_PATCH_TARGET, return_value=_mock_ticker_with_df(df)):
            rows = fetch_analyst_actions("AAPL")
        assert rows is not None
        assert rows[0]["action"] is None

    def test_fetch_failure_raises_and_reports_rate_limit(self, _patch_circuit_breaker):
        """FIXED 2026-08-19 (goal: "no SEC data" audit): a persistent rate-limit-shaped
        failure now gets one retry (see _fetch_with_circuit_breaker's own comment) before
        giving up, so a real, still-failing rate limit reports twice - once per attempt,
        each of which independently observes and reports the same rate-limit error."""
        with patch(_WORKER_PATCH_TARGET, return_value=_failing_worker(RuntimeError("Invalid Crumb (401)"))):
            with pytest.raises(RuntimeError, match="upgrades_downgrades fetch failed"):
                fetch_analyst_actions("AAPL")
        assert _patch_circuit_breaker.report_rate_limit_error.call_count == 2

    def test_fetch_failure_non_rate_limit_does_not_report_rate_limit(self, _patch_circuit_breaker):
        with patch(_WORKER_PATCH_TARGET, return_value=_failing_worker(ValueError("unexpected parse error"))):
            with pytest.raises(RuntimeError, match="upgrades_downgrades fetch failed"):
                fetch_analyst_actions("AAPL")
        _patch_circuit_breaker.report_rate_limit_error.assert_not_called()

    def test_success_reports_success_to_circuit_breaker(self, _patch_circuit_breaker):
        with patch(_WORKER_PATCH_TARGET, return_value=_mock_ticker_with_df(None)):
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
        worker = MagicMock()
        worker.fetch.side_effect = [TimeoutError("worker terminated"), df]
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            rows = fetch_analyst_actions("NVDA")

        assert rows is not None
        assert len(rows) == 1
        assert rows[0]["firm"] == "Morgan Stanley"
        # The circuit breaker must be re-checked on the retry, not just the first attempt.
        assert _patch_circuit_breaker.wait_or_raise.call_count == 2


class TestFetchForwardGrowthEstimates:
    """Regression tests for fetch_forward_growth_estimates() - covers Ticker.earnings_estimate/
    revenue_estimate/eps_trend, forward-looking analyst estimate signals this repo wasn't
    pulling before."""

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
        worker = _mock_worker_for(earnings_estimate=earnings_df, revenue_estimate=revenue_df, eps_trend=eps_trend_df)
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            result = fetch_forward_growth_estimates("AAPL")

        assert result is not None
        assert result["forward_eps_growth_current_fy"] == pytest.approx(0.1813)
        assert result["forward_eps_growth_next_fy"] == pytest.approx(0.0816)
        assert result["forward_revenue_growth_next_fy"] == pytest.approx(0.0991)
        # (8.81249 - 8.75324) / |8.75324| * 100
        assert result["eps_estimate_revision_90d_pct"] == pytest.approx(0.6769, abs=1e-3)

    def test_no_coverage_on_any_endpoint_returns_none(self, _patch_circuit_breaker):
        worker = _mock_worker_for(earnings_estimate=None, revenue_estimate=None, eps_trend=None)
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            assert fetch_forward_growth_estimates("ZZZZ") is None

        worker = _mock_worker_for(
            earnings_estimate=pd.DataFrame(), revenue_estimate=pd.DataFrame(), eps_trend=pd.DataFrame()
        )
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            assert fetch_forward_growth_estimates("ZZZZ") is None

    def test_partial_coverage_returns_whatever_is_available(self, _patch_circuit_breaker):
        """revenue_estimate/eps_trend missing but earnings_estimate present - a real,
        common partial-coverage shape, not an error. The 2 unavailable fields must be
        None, not silently dropped from the result dict."""
        earnings_df = pd.DataFrame({"avg": [8.81, 9.53], "growth": [0.1813, 0.0816]}, index=["0y", "+1y"])
        worker = _mock_worker_for(earnings_estimate=earnings_df, revenue_estimate=None, eps_trend=None)
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            result = fetch_forward_growth_estimates("AAPL")

        assert result is not None
        assert result["forward_eps_growth_current_fy"] == pytest.approx(0.1813)
        assert result["forward_eps_growth_next_fy"] == pytest.approx(0.0816)
        assert result["forward_revenue_growth_next_fy"] is None
        assert result["eps_estimate_revision_90d_pct"] is None

    def test_zero_prior_estimate_does_not_divide_by_zero(self, _patch_circuit_breaker):
        eps_trend_df = pd.DataFrame({"current": [0.05], "90daysAgo": [0.0]}, index=["0y"])
        worker = _mock_worker_for(earnings_estimate=None, revenue_estimate=None, eps_trend=eps_trend_df)
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            result = fetch_forward_growth_estimates("AAPL")
        assert result is None  # the only populated field is guarded off, so no_coverage

    def test_near_zero_prior_estimate_implausible_revision_is_suppressed(self, _patch_circuit_breaker):
        # ADDED 2026-08-30 (goal: full-data audit, live sanity-check pass): unlike the exact-zero
        # case above, a genuinely near-zero (but nonzero) prior estimate still passes the
        # `prior != 0` guard and blows up into a meaningless percentage - live-caught
        # -123,900.00% already on file. This is the ONE field in fetch_forward_growth_estimates
        # computed via a local division rather than reading yfinance's own pre-computed 'growth'
        # column, so it's uniquely exposed to this near-zero-denominator failure mode.
        eps_trend_df = pd.DataFrame({"current": [5.0], "90daysAgo": [0.001]}, index=["0y"])
        worker = _mock_worker_for(earnings_estimate=None, revenue_estimate=None, eps_trend=eps_trend_df)
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            result = fetch_forward_growth_estimates("AAPL")
        assert result is None  # the only populated field is guarded off, so no_coverage

    def test_plausible_revision_is_not_suppressed(self, _patch_circuit_breaker):
        # Control: a real, well-within-bound revision must still come through - the guard added
        # above must not reject legitimate values.
        eps_trend_df = pd.DataFrame({"current": [9.0], "90daysAgo": [8.0]}, index=["0y"])
        worker = _mock_worker_for(earnings_estimate=None, revenue_estimate=None, eps_trend=eps_trend_df)
        with patch(_WORKER_PATCH_TARGET, return_value=worker):
            result = fetch_forward_growth_estimates("AAPL")
        assert result is not None
        assert result["eps_estimate_revision_90d_pct"] == pytest.approx(12.5, abs=1e-3)
