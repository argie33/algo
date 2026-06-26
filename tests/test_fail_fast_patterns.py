#!/usr/bin/env python3
"""Test fail-fast patterns across loaders and dashboard.

Ensures critical data failures surface immediately instead of silent fallbacks.
Finance application correctness depends on these patterns.
"""

import pytest
from datetime import date
from unittest.mock import Mock, patch, MagicMock
import psycopg2


class TestEarningsCalendarFailFast:
    """Earnings calendar must fail-fast on unparseable dates."""

    def test_earnings_date_parse_error_raises(self):
        """Unparseable earnings date should raise, not continue."""
        from loaders.load_earnings_calendar import EarningsCalendarLoader
        from utils.external.yfinance import get_ticker

        loader = EarningsCalendarLoader()

        # Mock yfinance response with unparseable date
        mock_ticker = Mock()
        mock_ticker.calendar = {
            "Earnings Date": ["invalid-date-string"],
            "Earnings Average": 2.5,
            "Revenue Average": 1000000,
        }

        with patch("utils.external.yfinance.get_ticker", return_value=mock_ticker):
            with patch.object(loader, "_track_symbol_failure", return_value=False):  # Return False to stop retries
                # Should raise ValueError after retries are exhausted
                # (Previously would have silently continued with continue statement)
                with pytest.raises(ValueError, match="Unexpected error fetching earnings"):
                    loader.fetch_incremental("AAPL", date(2026, 1, 1))


class TestVIXFetcherFailFast:
    """VIX fetcher must fail-fast, no silent fallback to yfinance."""

    def test_vix_database_error_raises(self):
        """VIX database error should raise, not fallback to yfinance."""
        from loaders.market_health_fetchers import VIXFetcher
        from utils.db.context import DatabaseContext

        fetcher = VIXFetcher()

        # Mock database failure
        with patch("utils.db.context.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__.side_effect = (
                psycopg2.OperationalError("Database connection lost")
            )
            mock_db.return_value = mock_cursor

            # Should raise RuntimeError with CRITICAL message
            with pytest.raises(RuntimeError, match="\\[CRITICAL\\].*VIX data unavailable"):
                fetcher._fetch_vix_data(date(2026, 1, 1), date(2026, 1, 31))

    def test_vix_no_data_raises(self):
        """VIX with no data should raise, not fallback."""
        from loaders.market_health_fetchers import VIXFetcher
        from utils.db.context import DatabaseContext

        fetcher = VIXFetcher()

        # Mock database returning empty rows
        with patch("utils.db.context.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.__enter__.return_value.fetchall.return_value = []
            mock_cursor.__exit__.return_value = None
            mock_db.return_value = mock_cursor

            # Should raise RuntimeError
            with pytest.raises(RuntimeError, match="VIX data unavailable"):
                fetcher._fetch_vix_data(date(2026, 1, 1), date(2026, 1, 31))


class TestMarketHealthDailyFailFast:
    """Market health daily loader must fail-fast on no data."""

    def test_no_incremental_data_raises(self):
        """No incremental data should raise, not return error code."""
        from loaders.load_market_health_daily import MarketHealthDailyLoader

        loader = MarketHealthDailyLoader()

        # Mock fetch_incremental returning no rows
        with patch.object(loader, "fetch_incremental", return_value=None):
            # Should raise RuntimeError, not return code 1
            with pytest.raises(RuntimeError, match="MARKET_HEALTH.*No incremental data"):
                loader.load_symbol("SPY")


class TestDashboardKeyPressFailFast:
    """Dashboard keypress must fail-fast on terminal error."""

    def test_keypress_terminal_error_raises(self):
        """Terminal input failure should raise, not return empty string."""
        # This test verifies the behavior change
        # The _keypress function now raises on terminal errors instead of returning ""
        import sys

        # Simulate Unix-like system (not Windows)
        try:
            import termios
            import tty
            import select

            # Test that OSError in terminal handling raises
            with patch("select.select", return_value=([sys.stdin], [], [])):
                with patch("sys.stdin.fileno", side_effect=OSError("Terminal not available")):
                    from dashboard.dashboard import _keypress

                    # Should raise RuntimeError, not return ""
                    with pytest.raises(RuntimeError, match="Terminal input unavailable"):
                        _keypress()
        except ImportError:
            # Windows system, skip this test
            pytest.skip("Unix-only test")


class TestDashboardResponseHandling:
    """Dashboard must properly handle critical data errors."""

    def test_critical_errors_mapped_to_503(self):
        """Critical fetcher errors should map to 503 HTTP status."""
        from dashboard.response_handler import DashboardResponse, CRITICAL_FETCHERS

        results = {
            "run": {"_error": "API unavailable"},
            "cfg": {"config_key": "value"},
            "mkt": {"market_data": "available"},
        }

        response = DashboardResponse(results)

        # Critical error in 'run' should cause 503
        assert response.has_critical_errors()
        assert response.get_http_status_code() == 503

    def test_optional_errors_mapped_to_206(self):
        """Optional fetcher errors should map to 206 HTTP status."""
        from dashboard.response_handler import DashboardResponse

        results = {
            "run": {"status": "ok"},
            "cfg": {"config": "valid"},
            "mkt": {"market": "ok"},
            "port": {"portfolio": "ok"},
            "perf": {"performance": "ok"},
            "pos": {"positions": "ok"},
            "trades": {"trades": "ok"},
            "sig": {"signals": "ok"},
            "health": {"health": "ok"},
            "cb": {"circuit_breaker": "ok"},
            # Optional fetcher error
            "eco": {"_error": "Economic data unavailable"},
        }

        response = DashboardResponse(results)

        # No critical errors, only optional
        assert not response.has_critical_errors()
        assert response.optional_errors
        assert response.get_http_status_code() == 206

    def test_all_ok_mapped_to_200(self):
        """All successful fetchers should map to 200 HTTP status."""
        from dashboard.response_handler import DashboardResponse

        results = {
            "run": {"status": "ok"},
            "cfg": {"config": "valid"},
            "mkt": {"market": "ok"},
            "port": {"portfolio": "ok"},
            "perf": {"performance": "ok"},
            "pos": {"positions": "ok"},
            "trades": {"trades": "ok"},
            "sig": {"signals": "ok"},
            "health": {"health": "ok"},
            "cb": {"circuit_breaker": "ok"},
        }

        response = DashboardResponse(results)

        assert not response.has_errors()
        assert response.get_http_status_code() == 200


class TestErrorBoundary:
    """Error boundary must propagate errors, not hide them."""

    def test_error_detection(self):
        """Error dicts should be detected, not hidden."""
        from dashboard.error_boundary import has_error, safe_get, safe_list

        error_data = {"_error": "API unavailable"}

        # Error should be detected
        assert has_error(error_data)

        # safe_get should return error dict, not raise
        result = safe_get(error_data, "key")
        assert result == error_data

        # safe_list should detect error in dict and not hide it
        result = safe_list(error_data)
        # safe_list returns the error dict cast as list (intentional type cast)
        assert has_error(result)

    def test_malformed_data_raises(self):
        """Malformed response should raise, not fallback."""
        from dashboard.error_boundary import safe_get

        # Missing required key
        with pytest.raises(ValueError, match="missing required key"):
            safe_get({"wrong_key": "value"}, "expected_key")

        # Wrong type
        with pytest.raises(ValueError, match="Expected dict"):
            safe_get("not_a_dict", "key")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
