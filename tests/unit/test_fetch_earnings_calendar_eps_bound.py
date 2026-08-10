"""Regression: fetch_earnings_calendar() must reject absurd EPS magnitude values.

BUG FOUND 2026-08-10 (live-reproduced, morning pipeline reload): yfinance returned an
"EPS Estimate" of 2,180,000,000,000.0 ($2.18 trillion/share) for symbol ASTI - corrupt
source data, but with no magnitude bound this sailed straight into the DB write,
exceeding earnings_calendar.eps_estimate's numeric(12,4) column precision (~$99.9M max)
and raising a raw Postgres "numeric field overflow" for that symbol's entire COPY batch
instead of being caught and marked unavailable like every other real-fetch-failure path.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from utils.external.yfinance_analyst_ratings import fetch_earnings_calendar


def _mock_ticker_with_df(df):
    mock_ticker = MagicMock()
    mock_ticker.earnings_dates = df
    return mock_ticker


@pytest.fixture(autouse=True)
def _patch_circuit_breaker():
    with patch("utils.external.yfinance_analyst_ratings.get_circuit_breaker") as mock_get_cb:
        cb = MagicMock()
        mock_get_cb.return_value = cb
        yield cb


class TestFetchEarningsCalendarEpsBound:
    def test_absurd_eps_estimate_rejected_as_none(self, _patch_circuit_breaker):
        today = datetime.now(timezone.utc).date()
        df = pd.DataFrame(
            {"EPS Estimate": [2_180_000_000_000.0], "Reported EPS": [None], "Surprise(%)": [None]},
            index=pd.to_datetime([today.isoformat()]),
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(df)):
            rows = fetch_earnings_calendar("ASTI")

        assert rows is not None
        assert len(rows) == 1
        assert rows[0]["eps_estimate"] is None

    def test_absurd_actual_eps_rejected_as_none(self, _patch_circuit_breaker):
        today = datetime.now(timezone.utc).date()
        df = pd.DataFrame(
            {"EPS Estimate": [1.5], "Reported EPS": [-9_999_999_999.0], "Surprise(%)": [None]},
            index=pd.to_datetime([today.isoformat()]),
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(df)):
            rows = fetch_earnings_calendar("AAPL")

        assert rows is not None
        assert rows[0]["eps_estimate"] == 1.5
        assert rows[0]["actual_eps"] is None

    def test_normal_eps_values_pass_through_unchanged(self, _patch_circuit_breaker):
        today = datetime.now(timezone.utc).date()
        df = pd.DataFrame(
            {"EPS Estimate": [1.25], "Reported EPS": [1.30], "Surprise(%)": [4.0]},
            index=pd.to_datetime([today.isoformat()]),
        )
        with patch("yfinance.Ticker", return_value=_mock_ticker_with_df(df)):
            rows = fetch_earnings_calendar("AAPL")

        assert rows is not None
        assert rows[0]["eps_estimate"] == 1.25
        assert rows[0]["actual_eps"] == 1.30
        assert rows[0]["surprise_pct"] == 4.0
