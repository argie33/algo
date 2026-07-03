#!/usr/bin/env python3
"""Test fail-fast patterns across loaders and dashboard.

Ensures critical data failures surface immediately instead of silent fallbacks.
Finance application correctness depends on these patterns.
"""

from datetime import date
from unittest.mock import MagicMock, Mock, patch

import psycopg2
import pytest


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
            mock_cursor.__enter__.side_effect = psycopg2.OperationalError("Database connection lost")
            mock_db.return_value = mock_cursor

            # Should raise RuntimeError with CRITICAL message
            with pytest.raises(RuntimeError, match=r"\[CRITICAL\].*Failed to fetch VIX"):
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
            with pytest.raises(RuntimeError, match=r"\[CRITICAL\].*Failed to fetch VIX"):
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
            with pytest.raises(RuntimeError, match=r"MARKET_HEALTH.*No incremental data"):
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
            import select
            import termios
            import tty

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
        from dashboard.response_handler import CRITICAL_FETCHERS, DashboardResponse

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
        """Error dicts should be detected and raise, not hidden."""
        from dashboard.error_boundary import has_error, safe_get, safe_list

        error_data = {"_error": "API unavailable"}

        # Error should be detected
        assert has_error(error_data)

        # safe_get should raise on error dict (fail-fast behavior)
        with pytest.raises(ValueError, match="Data contains error"):
            safe_get(error_data, "key")

        # safe_list should detect error in dict and raise (not hide it)
        with pytest.raises(ValueError, match="Data contains error"):
            safe_list(error_data)

    def test_malformed_data_raises(self):
        """Malformed response should raise, not fallback."""
        from dashboard.error_boundary import safe_get

        # Missing required key
        with pytest.raises(ValueError, match="missing required key"):
            safe_get({"wrong_key": "value"}, "expected_key")

        # Wrong type
        with pytest.raises(ValueError, match="Expected dict"):
            safe_get("not_a_dict", "key")


class TestPositionMonitorSectorTrendFailFast:
    """Position monitor must fail-fast when sector trend data missing."""

    def test_sector_trend_missing_historical_data_raises(self):
        """Missing 4-week historical sector ranking should raise, not default to 'stable'."""
        from algo.monitoring.position_monitor import PositionMonitor

        config = {
            "stale_order_alert_minutes": "60",
            "stale_order_auto_cancel_minutes": "120",
        }
        monitor = PositionMonitor(config)

        # Mock database cursor for sector health check
        with patch("algo.monitoring.position_monitor.DatabaseContext") as mock_db_context:
            mock_cursor = MagicMock()
            # First call: fetch current sector data (success)
            # Second call: fetch 4-week ago sector data (missing)
            mock_cursor.fetchone.side_effect = [
                ("Technology",),  # company_profile sector lookup
                (1, date(2026, 6, 28)),  # current_rank lookup (succeeds)
                None,  # old_rank lookup (fails - returns None)
            ]
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__ = MagicMock(return_value=None)
            mock_db_context.return_value = mock_cursor

            # Should raise ValueError, not return "stable"
            with pytest.raises(ValueError, match=r"Cannot assess sector trend.*4-week historical baseline"):
                monitor._check_sector_health("AAPL", date(2026, 6, 28), mock_cursor)


class TestHaltFlagManagerFailFast:
    """Halt flag manager must fail-fast when halt reason missing."""

    def test_halt_flag_missing_reason_raises(self):
        """Missing halt reason should raise, not default to 'Unknown'."""
        from datetime import datetime, timezone

        from algo.orchestration.halt_flag_manager import HaltFlagManager

        mock_alerts = Mock()
        mock_log_phase_result = Mock()
        manager = HaltFlagManager(mock_alerts, mock_log_phase_result)

        # Use today's date for triggered_at so it matches the market open check
        today_utc = datetime.now(timezone.utc).isoformat()

        # Mock DynamoDB returning halt flag without reason
        with patch("boto3.resource") as mock_boto_resource:
            mock_table = MagicMock()
            mock_boto_resource.return_value.Table.return_value = mock_table
            mock_table.get_item.return_value = {
                "Item": {
                    "key": manager.HALT_FLAG_DYNAMODB_KEY,
                    "halt_flag": True,
                    "reason": None,  # Missing reason should cause error
                    "triggered_at": today_utc,
                }
            }

            # Should fail-closed: raise ValueError with CRITICAL message (not use default "Unknown")
            # The exception is caught and logged, fail-safe returns halt_flag=True
            with patch("algo.orchestration.halt_flag_manager.logger") as mock_logger:
                result = manager.check_halt_flag()
                # When missing reason, should fail-closed by returning True (halt=active)
                assert result is True
                # Verify CRITICAL error was logged (not silent fallback)
                assert any("CRITICAL" in str(call) for call in mock_logger.critical.call_args_list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
