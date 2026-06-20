#!/usr/bin/env python3
"""
Unit tests for exit engine intraday pricing fix.

Verifies that stop loss checking uses real-time quotes instead of stale daily closes.
"""

from datetime import date as _date
from unittest.mock import Mock, patch

import pytest

from algo.trading.exit_engine import ExitEngine


@pytest.fixture
def exit_engine(mock_config_minimal):
    """Create ExitEngine instance with minimal config."""
    with patch("algo.trading.exit_engine.TradeExecutor"):
        return ExitEngine(mock_config_minimal)


class TestAlpacaQuoteFetching:
    """Test fetching real-time quotes from Alpaca."""

    def test_fetch_alpaca_quote_success_with_bid_ask(self, exit_engine):
        """Test fetching quote when bid/ask available."""
        with (
            patch("algo.trading.exit_engine.get_alpaca_credentials") as mock_creds,
            patch("algo.trading.exit_engine.requests.get") as mock_get,
        ):
            # Setup credentials
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}

            # Setup Alpaca response with bid/ask
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "quotes": {
                    "AAPL": {
                        "bp": 150.00,  # bid price
                        "ap": 150.05,  # ask price
                        "lp": 150.02,  # last price (fallback)
                    }
                }
            }
            mock_get.return_value = mock_response

            # Fetch quote
            quote = exit_engine._fetch_alpaca_quote("AAPL")

            # Should return midpoint of bid/ask
            assert quote is not None
            assert quote == pytest.approx(150.025, rel=0.001)

    def test_fetch_alpaca_quote_success_with_last_price(self, exit_engine):
        """Test fetching quote when bid/ask unavailable but last price available."""
        with (
            patch("algo.trading.exit_engine.get_alpaca_credentials") as mock_creds,
            patch("algo.trading.exit_engine.requests.get") as mock_get,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "quotes": {
                    "AAPL": {
                        "lp": 150.02,  # last price only
                    }
                }
            }
            mock_get.return_value = mock_response

            quote = exit_engine._fetch_alpaca_quote("AAPL")

            # Should return last price
            assert quote is not None
            assert quote == pytest.approx(150.02, rel=0.001)

    def test_fetch_alpaca_quote_no_credentials(self, exit_engine):
        """Test quote fetch raises when credentials unavailable."""
        with patch("algo.trading.exit_engine.get_alpaca_credentials") as mock_creds:
            mock_creds.return_value = {"key": None, "secret": None}

            with pytest.raises(RuntimeError, match="Alpaca credentials missing"):
                exit_engine._fetch_alpaca_quote("AAPL")

    def test_fetch_alpaca_quote_api_failure(self, exit_engine):
        """Test quote fetch raises on API error."""
        with (
            patch("algo.trading.exit_engine.get_alpaca_credentials") as mock_creds,
            patch("algo.trading.exit_engine.requests.get") as mock_get,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}

            # Simulate API error
            mock_response = Mock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            with pytest.raises(RuntimeError, match="Alpaca quote API error"):
                exit_engine._fetch_alpaca_quote("AAPL")

    def test_fetch_alpaca_quote_timeout(self, exit_engine):
        """Test quote fetch raises on timeout."""
        import requests

        with (
            patch("algo.trading.exit_engine.get_alpaca_credentials") as mock_creds,
            patch("algo.trading.exit_engine.requests.get") as mock_get,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}

            # Simulate timeout
            mock_get.side_effect = requests.Timeout()

            with pytest.raises(RuntimeError, match="Alpaca quote API timeout"):
                exit_engine._fetch_alpaca_quote("AAPL")

    def test_fetch_alpaca_quote_market_open_no_data(self, exit_engine):
        """Test quote fetch raises when market is open but API returns no data."""
        with (
            patch("algo.trading.exit_engine.get_alpaca_credentials") as mock_creds,
            patch("algo.trading.exit_engine.requests.get") as mock_get,
            patch("algo.trading.exit_engine.MarketCalendar.is_market_open") as mock_market,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_market.return_value = True  # Market is open

            # Status 200 but no valid price data (empty quote)
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"quotes": {"AAPL": {}}}
            mock_get.return_value = mock_response

            # Should raise because market is open but we got no data
            with pytest.raises(RuntimeError, match=r"Market is open.*API issue"):
                exit_engine._fetch_alpaca_quote("AAPL")

    def test_fetch_alpaca_quote_market_closed_no_data(self, exit_engine):
        """Test quote fetch returns None when market is closed and API returns no data."""
        with (
            patch("algo.trading.exit_engine.get_alpaca_credentials") as mock_creds,
            patch("algo.trading.exit_engine.requests.get") as mock_get,
            patch("algo.trading.exit_engine.MarketCalendar.is_market_open") as mock_market,
        ):
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_market.return_value = False  # Market is closed

            # Status 200 but no valid price data (empty quote)
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"quotes": {"AAPL": {}}}
            mock_get.return_value = mock_response

            # Should return None because market is closed
            quote = exit_engine._fetch_alpaca_quote("AAPL")
            assert quote is None


class TestFetchRecentPrices:
    """Test the updated _fetch_recent_prices method with intraday support."""

    def test_fetch_recent_prices_uses_alpaca_quote_when_available(self, exit_engine):
        """Test that real-time quote is preferred over daily close."""
        current_date = _date(2025, 6, 14)

        # Mock Alpaca quote
        with patch.object(exit_engine, "_fetch_alpaca_quote") as mock_alpaca:
            mock_alpaca.return_value = 150.50  # Real-time price

            # Mock database cursor
            mock_cur = Mock()
            mock_cur.fetchone.return_value = (149.75,)  # Previous close

            # Fetch prices
            current_price, prev_close = exit_engine._fetch_recent_prices(mock_cur, "AAPL", current_date)

            # Should use Alpaca quote for current price
            assert current_price == 150.50
            assert prev_close == 149.75

    def test_fetch_recent_prices_falls_back_to_daily_when_alpaca_unavailable(self, exit_engine):
        """Test that daily closes are used when Alpaca is unavailable."""
        current_date = _date(2025, 6, 14)

        # Mock Alpaca failing
        with patch.object(exit_engine, "_fetch_alpaca_quote") as mock_alpaca:
            mock_alpaca.return_value = None  # Alpaca unavailable

            # Mock database cursor
            mock_cur = Mock()
            mock_cur.fetchall.return_value = [
                (_date(2025, 6, 14), 149.80),  # Today's close
                (_date(2025, 6, 13), 149.75),  # Yesterday's close
            ]

            # Fetch prices
            current_price, prev_close = exit_engine._fetch_recent_prices(mock_cur, "AAPL", current_date)

            # Should use daily closes from database
            assert current_price == 149.80
            assert prev_close == 149.75

    def test_fetch_recent_prices_raises_on_missing_data(self, exit_engine):
        """Test that missing price data raises error (fail-closed)."""
        current_date = _date(2025, 6, 14)

        with patch.object(exit_engine, "_fetch_alpaca_quote") as mock_alpaca:
            mock_alpaca.return_value = None

            # Mock database with no data
            mock_cur = Mock()
            mock_cur.fetchall.return_value = []

            # Should raise error when price data unavailable, not return None
            with pytest.raises(RuntimeError, match="Price data missing"):
                exit_engine._fetch_recent_prices(mock_cur, "AAPL", current_date)

    def test_fetch_recent_prices_propagates_alpaca_error(self, exit_engine):
        """Test that API errors from Alpaca are propagated to caller."""
        current_date = _date(2025, 6, 14)

        with patch.object(exit_engine, "_fetch_alpaca_quote") as mock_alpaca:
            # Simulate Alpaca API error (market open, no data)
            mock_alpaca.side_effect = RuntimeError("Alpaca quote API returned status 200 but no valid price data")

            mock_cur = Mock()

            # Should raise, not fall back to daily closes
            with pytest.raises(RuntimeError, match="no valid price data"):
                exit_engine._fetch_recent_prices(mock_cur, "AAPL", current_date)


class TestStopExecutionWithIntradayPrices:
    """Integration tests for stop execution using intraday prices."""

    def test_stop_execution_uses_intraday_price_not_daily_close(self, exit_engine):
        """Test that stops are evaluated against intraday prices."""
        current_date = _date(2025, 6, 14)
        stop_price = 145.00
        intraday_price = 144.50  # Below stop

        with patch.object(exit_engine, "_fetch_alpaca_quote") as mock_alpaca:
            mock_alpaca.return_value = intraday_price

            mock_cur = Mock()
            mock_cur.fetchone.return_value = (149.00,)  # Previous close

            current_price, _ = exit_engine._fetch_recent_prices(mock_cur, "AAPL", current_date)

            # Should use intraday price (144.50), not stale daily close
            assert current_price == 144.50
            assert current_price < stop_price  # Stop should trigger


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
