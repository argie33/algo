"""Regression/coverage test for algo/trading/quote_fetcher.py's fetch_live_quote() - found
2026-08-31 to have ZERO test coverage anywhere in the suite despite being live, critical code:
called from position_monitor.py's health-flag early-exit path (the exact function this module
was extracted from exit_engine.py to fix - see this module's own docstring for the live-
reproduced $0.00 P&L fabrication bug that motivated the extraction) AND from
scripts/flatten_all_positions.py, the emergency kill-switch tool. A bug here could silently
affect both routine position monitoring and the one tool an operator reaches for when something
has already gone wrong.

Mirrors the retry/fallback contract already tested for the sibling
ExitEngine._fetch_alpaca_quote in test_exit_engine_quote_retries_transient_errors.py - this is
the shared, extracted version of that same logic, and untested paths here could silently diverge
from that already-verified behavior over time.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from algo.trading.exceptions import ExchangeAPIError
from algo.trading.quote_fetcher import fetch_live_quote


def _quote_response(status_code=200, bp=100.0, ap=100.5, lp=None, quotes_override=None, missing_quotes_key=False):
    resp = MagicMock(status_code=status_code)
    if missing_quotes_key:
        resp.json.return_value = {}
    elif quotes_override is not None:
        resp.json.return_value = {"quotes": quotes_override}
    else:
        quote: dict[str, float] = {}
        if bp is not None:
            quote["bp"] = bp
        if ap is not None:
            quote["ap"] = ap
        if lp is not None:
            quote["lp"] = lp
        resp.json.return_value = {"quotes": {"AAPL": quote}}
    return resp


class TestFetchLiveQuoteHappyPath:
    def test_returns_bid_ask_midpoint(self):
        resp = _quote_response(200, bp=100.0, ap=100.5)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 100.25

    def test_falls_back_to_last_price_when_no_bid_ask(self):
        resp = _quote_response(200, bp=None, ap=None, lp=99.75)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 99.75

    def test_zero_bid_ask_falls_back_to_last_price(self):
        """bp/ap present but zero (e.g. a halted/illiquid symbol) must not be treated as a
        valid midpoint - 0/0 would silently report a $0.00 price."""
        resp = _quote_response(200, bp=0, ap=0, lp=50.0)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 50.0


class TestFetchLiveQuoteSpreadSanityGuard:
    """Regression coverage for a CRITICAL real-money-readiness bug (found 2026-09-06):
    the bid/ask midpoint used to be returned whenever both sides were present and
    positive, with no check on how far apart they actually are. A wildly wide spread (a
    thin/halted/broken quote) produced a garbage midpoint fed directly into real-time
    exit/stop decisions (position_monitor.py's health-flag exits, exit_engine.py's
    stop/target checks)."""

    def test_narrow_spread_returns_midpoint(self):
        resp = _quote_response(200, bp=100.0, ap=100.5)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 100.25

    def test_wide_spread_falls_back_to_last_price_not_midpoint(self):
        """bid=$1, ask=$100 -> a 99% relative spread must not be trusted as a midpoint."""
        resp = _quote_response(200, bp=1.0, ap=100.0, lp=2.0)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 2.0

    def test_wide_spread_with_no_last_price_raises(self):
        """No safe price at all (wide spread, no last trade) must fail closed, not return
        the untrustworthy midpoint."""
        resp = _quote_response(200, bp=1.0, ap=100.0, lp=None)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=True),
            pytest.raises(RuntimeError),
        ):
            fetch_live_quote("AAPL", execution_mode="auto")


class TestFetchLiveQuoteNoValidPriceData:
    def test_no_price_data_market_open_raises(self):
        resp = _quote_response(200, bp=None, ap=None, lp=None)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=True),
        ):
            with pytest.raises(RuntimeError, match="API issue"):
                fetch_live_quote("AAPL", execution_mode="auto")

    def test_no_price_data_market_closed_raises_different_message(self):
        resp = _quote_response(200, bp=None, ap=None, lp=None)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=False),
        ):
            with pytest.raises(RuntimeError, match="market closed"):
                fetch_live_quote("AAPL", execution_mode="auto")

    def test_missing_quotes_key_raises(self):
        resp = _quote_response(200, missing_quotes_key=True)
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            with pytest.raises(RuntimeError, match="missing 'quotes' key"):
                fetch_live_quote("AAPL", execution_mode="auto")

    def test_symbol_not_in_quotes_raises(self):
        resp = _quote_response(200, quotes_override={"MSFT": {"bp": 1, "ap": 1}})
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            with pytest.raises(RuntimeError, match="no data for AAPL"):
                fetch_live_quote("AAPL", execution_mode="auto")


class TestFetchLiveQuote401:
    def test_401_auto_mode_raises_critical(self):
        resp = MagicMock(status_code=401, text="unauthorized")
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            with pytest.raises(RuntimeError, match="401"):
                fetch_live_quote("AAPL", execution_mode="auto")

    def test_401_paper_mode_returns_data_unavailable(self):
        resp = MagicMock(status_code=401, text="unauthorized")
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            result = fetch_live_quote("AAPL", execution_mode="paper")
        assert isinstance(result, dict)
        assert result.get("data_unavailable") is True


class TestFetchLiveQuote404:
    def test_404_auto_mode_raises_critical(self):
        resp = MagicMock(status_code=404, text="not found")
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            with pytest.raises(RuntimeError, match="delisted"):
                fetch_live_quote("AAPL", execution_mode="auto")

    def test_404_paper_mode_returns_data_unavailable(self):
        resp = MagicMock(status_code=404, text="not found")
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            result = fetch_live_quote("AAPL", execution_mode="dry")
        assert isinstance(result, dict)
        assert result.get("data_unavailable") is True


class TestFetchLiveQuoteRetries:
    def test_429_then_success_retries(self):
        rate_limited = MagicMock(status_code=429, text="rate limited")
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch(
                "algo.trading.quote_fetcher.requests.get",
                side_effect=[rate_limited, _quote_response(200)],
            ),
            patch("algo.trading.quote_fetcher.time.sleep") as mock_sleep,
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 100.25
        mock_sleep.assert_called_once()

    def test_503_exhausts_retries_then_raises(self):
        unavailable = MagicMock(status_code=503, text="unavailable")
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=unavailable) as mock_get,
            patch("algo.trading.quote_fetcher.time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="503"):
                fetch_live_quote("AAPL", execution_mode="auto")
        assert mock_get.call_count == 3

    def test_timeout_then_success_retries(self):
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch(
                "algo.trading.quote_fetcher.requests.get",
                side_effect=[requests.Timeout("timed out"), _quote_response(200)],
            ),
            patch("algo.trading.quote_fetcher.time.sleep") as mock_sleep,
        ):
            price = fetch_live_quote("AAPL", execution_mode="auto")
        assert price == 100.25
        mock_sleep.assert_called_once()

    def test_connection_error_exhausts_retries_raises_exchange_api_error(self):
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch(
                "algo.trading.quote_fetcher.requests.get",
                side_effect=requests.ConnectionError("connection reset"),
            ) as mock_get,
            patch("algo.trading.quote_fetcher.time.sleep"),
        ):
            with pytest.raises(ExchangeAPIError):
                fetch_live_quote("AAPL", execution_mode="auto")
        assert mock_get.call_count == 3


class TestFetchLiveQuoteMisc:
    def test_missing_credentials_raises(self):
        with patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": None, "secret": None}):
            with pytest.raises(RuntimeError, match="credentials missing"):
                fetch_live_quote("AAPL", execution_mode="auto")

    def test_generic_error_status_raises(self):
        resp = MagicMock(status_code=500, text="server error")
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", return_value=resp),
        ):
            with pytest.raises(RuntimeError, match="500"):
                fetch_live_quote("AAPL", execution_mode="auto")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
