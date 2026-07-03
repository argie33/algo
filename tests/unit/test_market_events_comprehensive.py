#!/usr/bin/env python3
"""Comprehensive tests for market_events.py (safety-critical module).

MarketEventHandler detects trading halts, circuit breakers, and market anomalies.
These tests ensure fail-safe behavior and correct circuit breaker boundary detection.
"""

import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from algo.infrastructure.market_events import MarketEventHandler


class TestMarketEventHandlerInit:
    """Test MarketEventHandler initialization."""

    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_init_with_credentials(self, mock_base_url, mock_cred_manager):
        """Test handler initialization with valid credentials."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "test_key", "secret": "test_secret"}
        mock_cred_manager.return_value = mock_cm

        config = MagicMock()
        handler = MarketEventHandler(config)

        assert handler.config == config
        assert handler.alpaca_base_url == "https://api.alpaca.markets"
        assert handler.alpaca_key == "test_key"
        assert handler.alpaca_secret == "test_secret"

    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_init_stores_config(self, mock_base_url, mock_cred_manager):
        """Test that config is stored and accessible."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        config = {"threshold": 0.05}
        handler = MarketEventHandler(config)

        assert handler.config == {"threshold": 0.05}


class TestCheckSingleStockHalt:
    """Test check_single_stock_halt() method."""

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_halt_detected_tradable_false(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test detection when tradable=False indicates halt."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "HALTED", "tradable": False}
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_single_stock_halt("AAPL")

        assert result is not None
        assert result["halted"] is True
        assert result["symbol"] == "AAPL"
        assert result["status"] == "HALTED"
        assert result["tradable"] is False
        assert "timestamp" in result

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_halt_detected_status_inactive(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test detection when status=INACTIVE indicates halt."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "INACTIVE", "tradable": True}
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_single_stock_halt("XYZ")

        assert result is not None
        assert result["halted"] is True
        assert result["status"] == "INACTIVE"

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_not_halted_active_tradable(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test no halt when status=ACTIVE and tradable=True."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ACTIVE", "tradable": True}
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_single_stock_halt("AAPL")

        assert result is not None
        assert result["halted"] is False
        assert result["symbol"] == "AAPL"
        assert result["status"] == "ACTIVE"
        assert result["tradable"] is True

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_api_error_status_code_404(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test error handling for API non-200 response."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_single_stock_halt("INVALID")

        # Code catches RuntimeError and returns error dict (graceful degradation)
        assert result is not None
        assert result.get("error") == "halt_check_failed"
        assert result.get("reason") == "data_validation_error"

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_json_decode_error(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test error handling for malformed JSON."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_single_stock_halt("AAPL")

        # Code catches RuntimeError and returns error dict (graceful degradation)
        assert result is not None
        assert result.get("error") == "halt_check_failed"
        assert result.get("reason") == "data_validation_error"

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_missing_status_field(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test error when 'status' field is missing from response."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tradable": True}
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_single_stock_halt("AAPL")

        # Code catches ValueError and returns error dict (graceful degradation)
        assert result is not None
        assert result.get("error") == "halt_check_failed"
        assert result.get("reason") == "data_validation_error"
        assert "status" in result.get("description", "")

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_missing_tradable_field(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test error when 'tradable' field is missing from response."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ACTIVE"}
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_single_stock_halt("AAPL")

        # Code catches ValueError and returns error dict (graceful degradation)
        assert result is not None
        assert result.get("error") == "halt_check_failed"
        assert result.get("reason") == "data_validation_error"
        assert "tradable" in result.get("description", "")

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_request_exception_network_error(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test error handling for network timeouts."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_get.side_effect = requests.Timeout("Connection timed out")

        handler = MarketEventHandler({})
        result = handler.check_single_stock_halt("AAPL")

        # Code catches Timeout and returns error dict (graceful degradation)
        assert result is not None
        assert result.get("error") == "halt_check_failed"
        assert result.get("reason") == "api_timeout"


class TestCheckMarketCircuitBreaker:
    """Test check_market_circuit_breaker() method - critical circuit breaker detection."""

    @patch("algo.infrastructure.market_events.ThreadPoolExecutor")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_circuit_breaker_level_3_triggered_20_percent(self, mock_base_url, mock_cred_manager, mock_executor):
        """Test Level 3 (20%+ down) detection."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        # Setup mock executor and futures
        def fetch_quotes():
            return 300.0  # Current price

        def fetch_bars():
            return 375.0  # Open price: (375-300)/375 = 20% down

        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_context
        mock_context.__exit__.return_value = None

        def side_effect(*args, **kwargs):
            return mock_context

        mock_executor.return_value = mock_context
        mock_context.submit.side_effect = [
            MagicMock(result=lambda t: fetch_quotes()),
            MagicMock(result=lambda t: fetch_bars()),
        ]

        handler = MarketEventHandler({})

        # We need to mock the thread pool execution
        with patch("algo.infrastructure.market_events.ThreadPoolExecutor") as mock_pool:
            mock_context = MagicMock()
            mock_pool.return_value.__enter__.return_value = mock_context

            quote_future = MagicMock()
            quote_future.result.return_value = 300.0
            bars_future = MagicMock()
            bars_future.result.return_value = 375.0

            mock_context.submit.side_effect = [quote_future, bars_future]

            result = handler.check_market_circuit_breaker()

        assert result is not None
        assert result["level"] == 3
        assert result["pct_down"] == 20.0
        assert result["action"] == "HALT_ALL_ENTRIES"
        assert "timestamp" in result

    @patch("algo.infrastructure.market_events.ThreadPoolExecutor")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_circuit_breaker_level_2_triggered_13_percent(self, mock_base_url, mock_cred_manager, mock_executor):
        """Test Level 2 (13%+ down) detection."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        with patch("algo.infrastructure.market_events.ThreadPoolExecutor") as mock_pool:
            mock_context = MagicMock()
            mock_pool.return_value.__enter__.return_value = mock_context

            quote_future = MagicMock()
            quote_future.result.return_value = 435.0  # Current
            bars_future = MagicMock()
            bars_future.result.return_value = 500.0  # Open: (500-435)/500 = 13% down

            mock_context.submit.side_effect = [quote_future, bars_future]

            handler = MarketEventHandler({})
            result = handler.check_market_circuit_breaker()

        assert result is not None
        assert result["level"] == 2
        assert result["pct_down"] == 13.0
        assert result["action"] == "PAUSE_NEW_ENTRIES_15MIN"

    @patch("algo.infrastructure.market_events.ThreadPoolExecutor")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_circuit_breaker_level_1_triggered_7_percent(self, mock_base_url, mock_cred_manager, mock_executor):
        """Test Level 1 (7%+ down) detection."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        with patch("algo.infrastructure.market_events.ThreadPoolExecutor") as mock_pool:
            mock_context = MagicMock()
            mock_pool.return_value.__enter__.return_value = mock_context

            quote_future = MagicMock()
            quote_future.result.return_value = 465.0  # Current
            bars_future = MagicMock()
            bars_future.result.return_value = 500.0  # Open: (500-465)/500 = 7% down

            mock_context.submit.side_effect = [quote_future, bars_future]

            handler = MarketEventHandler({})
            result = handler.check_market_circuit_breaker()

        assert result is not None
        assert result["level"] == 1
        assert result["pct_down"] == 7.0
        assert result["action"] == "PAUSE_NEW_ENTRIES_15MIN"

    @patch("algo.infrastructure.market_events.ThreadPoolExecutor")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_no_circuit_breaker_less_than_7_percent(self, mock_base_url, mock_cred_manager, mock_executor):
        """Test no circuit breaker triggered when down < 7%."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        with patch("algo.infrastructure.market_events.ThreadPoolExecutor") as mock_pool:
            mock_context = MagicMock()
            mock_pool.return_value.__enter__.return_value = mock_context

            quote_future = MagicMock()
            quote_future.result.return_value = 485.0  # Current
            bars_future = MagicMock()
            bars_future.result.return_value = 500.0  # Open: (500-485)/500 = 3% down

            mock_context.submit.side_effect = [quote_future, bars_future]

            handler = MarketEventHandler({})
            result = handler.check_market_circuit_breaker()

        assert result is None

    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_circuit_breaker_no_credentials_skip_check(self, mock_base_url, mock_cred_manager):
        """Test that check is skipped when Alpaca credentials are not configured."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": None, "secret": None}
        mock_cred_manager.return_value = mock_cm

        handler = MarketEventHandler({})
        handler.alpaca_key = None
        handler.alpaca_secret = None

        result = handler.check_market_circuit_breaker()

        # Code returns error dict when credentials missing (graceful degradation)
        assert result is not None
        assert result.get("error") == "circuit_breaker_check_failed"
        assert result.get("reason") == "credentials_not_configured"

    @patch("algo.infrastructure.market_events.ThreadPoolExecutor")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_circuit_breaker_missing_prices(self, mock_base_url, mock_cred_manager, mock_executor):
        """Test error when prices are missing."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        with patch("algo.infrastructure.market_events.ThreadPoolExecutor") as mock_pool:
            mock_context = MagicMock()
            mock_pool.return_value.__enter__.return_value = mock_context

            quote_future = MagicMock()
            quote_future.result.return_value = None  # Missing current price
            bars_future = MagicMock()
            bars_future.result.return_value = 500.0

            mock_context.submit.side_effect = [quote_future, bars_future]

            handler = MarketEventHandler({})
            result = handler.check_market_circuit_breaker()

            # Code catches RuntimeError and returns error dict (graceful degradation)
            assert result is not None
            assert result.get("error") == "circuit_breaker_check_failed"
            assert result.get("reason") == "data_validation_error"


class TestCheckEarlyClose:
    """Test check_early_close() method."""

    @patch("algo.infrastructure.market_events.DatabaseContext")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_early_close_true(self, mock_base_url, mock_cred_manager, mock_db):
        """Test detection of early close day."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (True,)
        mock_db.return_value.__enter__.return_value = mock_cursor

        handler = MarketEventHandler({})
        check_date = date(2024, 11, 29)  # Day after Thanksgiving
        result = handler.check_early_close(check_date)

        assert result is True

    @patch("algo.infrastructure.market_events.DatabaseContext")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_early_close_false(self, mock_base_url, mock_cred_manager, mock_db):
        """Test normal close day."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (False,)
        mock_db.return_value.__enter__.return_value = mock_cursor

        handler = MarketEventHandler({})
        check_date = date(2024, 11, 27)  # Regular trading day
        result = handler.check_early_close(check_date)

        assert result is False

    @patch("algo.infrastructure.market_events.DatabaseContext")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_early_close_missing_record(self, mock_base_url, mock_cred_manager, mock_db):
        """Test error when market_health_daily record is missing."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db.return_value.__enter__.return_value = mock_cursor

        handler = MarketEventHandler({})
        check_date = date(2024, 11, 27)

        with pytest.raises(RuntimeError, match="Cannot verify early close status"):
            handler.check_early_close(check_date)


class TestCheckAfterHoursWindow:
    """Test check_after_hours_window() method."""

    @patch("algo.infrastructure.market_events.DatabaseContext")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_after_hours_normal_day_15_45(self, mock_base_url, mock_cred_manager, mock_db):
        """Test after-hours detection at 15:45 ET on normal trading day."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (False,)  # Not an early close
        mock_db.return_value.__enter__.return_value = mock_cursor

        handler = MarketEventHandler({})

        # Create an Eastern time at 15:45
        from utils.infrastructure import EASTERN_TZ

        check_time = datetime(2024, 11, 27, 15, 45, 0, tzinfo=EASTERN_TZ)
        result = handler.check_after_hours_window(check_time)

        assert result is True

    @patch("algo.infrastructure.market_events.DatabaseContext")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_after_hours_normal_day_15_44(self, mock_base_url, mock_cred_manager, mock_db):
        """Test before after-hours at 15:44 ET on normal trading day."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (False,)
        mock_db.return_value.__enter__.return_value = mock_cursor

        handler = MarketEventHandler({})

        from utils.infrastructure import EASTERN_TZ

        check_time = datetime(2024, 11, 27, 15, 44, 0, tzinfo=EASTERN_TZ)
        result = handler.check_after_hours_window(check_time)

        assert result is False

    @patch("algo.infrastructure.market_events.DatabaseContext")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_after_hours_early_close_day_13_00(self, mock_base_url, mock_cred_manager, mock_db):
        """Test after-hours at 13:00 ET on early close day."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (True,)  # Early close day
        mock_db.return_value.__enter__.return_value = mock_cursor

        handler = MarketEventHandler({})

        from utils.infrastructure import EASTERN_TZ

        check_time = datetime(2024, 11, 29, 13, 0, 0, tzinfo=EASTERN_TZ)
        result = handler.check_after_hours_window(check_time)

        assert result is True

    @patch("algo.infrastructure.market_events.DatabaseContext")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_after_hours_early_close_day_12_59(self, mock_base_url, mock_cred_manager, mock_db):
        """Test before after-hours at 12:59 ET on early close day."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (True,)
        mock_db.return_value.__enter__.return_value = mock_cursor

        handler = MarketEventHandler({})

        from utils.infrastructure import EASTERN_TZ

        check_time = datetime(2024, 11, 29, 12, 59, 0, tzinfo=EASTERN_TZ)
        result = handler.check_after_hours_window(check_time)

        assert result is False


class TestHandleSingleStockHalt:
    """Test handle_single_stock_halt() method."""

    @patch("utils.db.DatabaseContext")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_handle_halt_cancels_pending_orders(self, mock_base_url, mock_cred_manager, mock_db):
        """Test that halt handler cancels pending orders."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.__exit__.return_value = None

        handler = MarketEventHandler({})
        result = handler.handle_single_stock_halt("AAPL")

        assert result is not None
        assert result["action"] == "HALT_SYMBOL"
        assert result["symbol"] == "AAPL"
        assert result["status"] == "orders_cancelled"
        assert "timestamp" in result

        # Verify SQL was executed for cancellation and logging
        assert mock_cursor.execute.call_count >= 2


class TestCheckDelisting:
    """Test check_delisting() method."""

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_delisted_status_detected(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test detection of delisted status."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "DELISTED"}
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_delisting("OldStock")

        assert result is not None
        assert result["delisted"] is True
        assert result["symbol"] == "OldStock"
        assert result["status"] == "DELISTED"
        assert result["action"] == "FORCE_EXIT_MARKET"

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_inactive_status_detected(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test detection of inactive status."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "INACTIVE"}
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_delisting("OLDSTOCK")

        assert result is not None
        assert result["delisted"] is True
        assert result["status"] == "INACTIVE"

    @patch("algo.infrastructure.market_events.requests.get")
    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    @patch("algo.infrastructure.market_events.get_api_timeout")
    def test_active_stock_not_delisted(self, mock_timeout, mock_base_url, mock_cred_manager, mock_get):
        """Test active stock returns None."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_timeout.return_value = 10
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ACTIVE"}
        mock_get.return_value = mock_response

        handler = MarketEventHandler({})
        result = handler.check_delisting("AAPL")

        assert result is None


class TestRunPreMarketChecks:
    """Test run_pre_market_checks() concurrent execution."""

    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_pre_market_checks_all_pass(self, mock_base_url, mock_cred_manager):
        """Test all pre-market checks passing."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        handler = MarketEventHandler({})

        # Mock the actual methods since ThreadPoolExecutor is hard to mock
        with (
            patch.object(handler, "check_early_close", return_value=False),
            patch.object(handler, "check_market_circuit_breaker", return_value=None),
            patch.object(handler, "check_after_hours_window", return_value=False),
        ):
            result = handler.run_pre_market_checks()

        assert "timestamp" in result
        assert "checks" in result
        assert "alerts" in result
        assert result["checks"]["early_close"] is False
        assert result["checks"]["circuit_breaker"] is None
        assert result["checks"]["after_hours_window"] is False

    @patch("algo.infrastructure.market_events.get_credential_manager")
    @patch("algo.infrastructure.market_events.get_alpaca_base_url")
    def test_pre_market_checks_with_circuit_breaker_alert(self, mock_base_url, mock_cred_manager):
        """Test pre-market checks with circuit breaker triggered."""
        mock_base_url.return_value = "https://api.alpaca.markets"
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm

        handler = MarketEventHandler({})
        cb_result = {
            "level": 1,
            "description": "7%+ down - 15-minute halt",
            "pct_down": 7.5,
            "action": "PAUSE_NEW_ENTRIES_15MIN",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Mock the actual methods
        with (
            patch.object(handler, "check_early_close", return_value=False),
            patch.object(handler, "check_market_circuit_breaker", return_value=cb_result),
            patch.object(handler, "check_after_hours_window", return_value=False),
        ):
            result = handler.run_pre_market_checks()

        assert "timestamp" in result
        assert "checks" in result
        assert "alerts" in result
        assert result["checks"]["circuit_breaker"] == cb_result
        # Should have alert about circuit breaker
        assert any("CIRCUIT BREAKER LEVEL 1" in str(alert) for alert in result["alerts"])
