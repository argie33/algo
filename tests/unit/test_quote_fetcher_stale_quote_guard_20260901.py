"""Regression test: fetch_live_quote() must reject a quote whose own Alpaca-provided
timestamp ("t") is stale while the market is open, instead of trusting an HTTP 200
response unconditionally.

Before this fix, a bid/ask/last-price present and >0 was treated as sufficient - but a
frozen free-tier IEX feed can keep returning the LAST quote it ever received with a 200
status, indistinguishable from a genuinely fresh one to every prior check. This function
feeds real-time exit/stop evaluation (position_monitor.py) - a silently stale price there
defeats the entire point of this module (see its own docstring: extracted specifically to
fix a stale-price P&L fabrication bug in the health-flag early-exit path).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from algo.trading.quote_fetcher import fetch_live_quote


def _quote_response_with_timestamp(quote_dt: datetime, bp=100.0, ap=100.5):
    resp = MagicMock(status_code=200)
    ts_str = quote_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    resp.json.return_value = {"quotes": {"AAPL": {"bp": bp, "ap": ap, "t": ts_str}}}
    return resp


class TestFetchLiveQuoteStalenessGuard:
    def test_stale_quote_market_open_raises(self):
        stale_dt = datetime.now(timezone.utc) - timedelta(minutes=10)
        resp = _quote_response_with_timestamp(stale_dt)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=True),
        ):
            with pytest.raises(RuntimeError, match="stale"):
                fetch_live_quote("AAPL", execution_mode="auto")

    def test_fresh_quote_market_open_succeeds(self):
        fresh_dt = datetime.now(timezone.utc) - timedelta(seconds=2)
        resp = _quote_response_with_timestamp(fresh_dt)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=True),
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 100.25

    def test_stale_quote_market_closed_does_not_raise_on_staleness(self):
        """No new quotes are expected while the market is closed - staleness must not be
        enforced there (only the existing 'no price data at all' check applies)."""
        stale_dt = datetime.now(timezone.utc) - timedelta(hours=12)
        resp = _quote_response_with_timestamp(stale_dt)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=False),
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 100.25

    def test_unparseable_timestamp_logs_and_proceeds(self):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"quotes": {"AAPL": {"bp": 100.0, "ap": 100.5, "t": "not-a-timestamp"}}}
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=True),
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 100.25
