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

from utils.external.yfinance_analyst_ratings import fetch_analyst_actions


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
