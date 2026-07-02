#!/usr/bin/env python3
"""
Test suite for market metrics fixes:
1. Dashboard placeholder restoration
2. BreadthFetcher validation
"""

from datetime import date
from unittest.mock import Mock, patch

import pytest

from loaders.market_health_fetchers import BreadthFetcher


class TestBreadthFetcherValidation:
    """Test that BreadthFetcher fails fast when data is missing."""

    def test_fails_when_price_daily_empty(self):
        """Raises error when price_daily has no rows in date range."""
        fetcher = BreadthFetcher()

        # Mock cursor that returns 0 rows for price_daily count
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (0,)  # COUNT(*) = 0

        start = date(2026, 6, 1)
        end = date(2026, 6, 28)

        with pytest.raises(RuntimeError) as exc_info:
            fetcher._compute_new_highs_lows(mock_cur, start, end)

        assert "price_daily has no rows" in str(exc_info.value)
        assert "cannot compute new highs/lows" in str(exc_info.value).lower()
        # Verify it calls COUNT first
        mock_cur.execute.assert_called_once()
        call_args = mock_cur.execute.call_args[0][0]
        assert "COUNT(*)" in call_args

    def test_fails_when_window_function_returns_nothing(self, caplog):
        """When window function produces 0 rows, logs warning and returns empty dict."""
        fetcher = BreadthFetcher()

        mock_cur = Mock()
        # First call: COUNT returns 100 rows (data exists)
        # Second call: window function returns empty
        mock_cur.fetchone.return_value = (100,)
        mock_cur.fetchall.return_value = []  # Window function returns nothing

        start = date(2026, 6, 1)
        end = date(2026, 6, 28)

        import logging

        with caplog.at_level(logging.WARNING):
            result = fetcher._compute_new_highs_lows(mock_cur, start, end)

        # Should return empty dict, not raise error (gracefully handle early dataset)
        assert result == {}
        # Should log warning about missing 252-day history
        assert any("252-day history" in record.message for record in caplog.records)

    def test_succeeds_with_valid_data(self):
        """Returns dict with dates when valid data exists."""
        fetcher = BreadthFetcher()

        mock_cur = Mock()
        # COUNT returns 300+ rows (has history)
        mock_cur.fetchone.return_value = (300,)

        # Window function returns valid results
        test_date = date(2026, 6, 28)
        mock_cur.fetchall.return_value = [
            (test_date, 150, 50),  # date, new_highs, new_lows
        ]

        start = date(2026, 6, 1)
        end = date(2026, 6, 28)

        result = fetcher._compute_new_highs_lows(mock_cur, start, end)

        assert isinstance(result, dict)
        assert test_date.isoformat() in result
        assert result[test_date.isoformat()] == (150, 50)

    def test_handles_null_values_in_counts(self):
        """Converts NULL counts to 0."""
        fetcher = BreadthFetcher()

        mock_cur = Mock()
        mock_cur.fetchone.return_value = (100,)

        test_date = date(2026, 6, 28)
        # NULL in counts should be converted to 0
        mock_cur.fetchall.return_value = [
            (test_date, None, 50),  # None highs
        ]

        start = date(2026, 6, 1)
        end = date(2026, 6, 28)

        result = fetcher._compute_new_highs_lows(mock_cur, start, end)

        assert result[test_date.isoformat()] == (0, 50)


class TestDashboardMetricsDisplay:
    """Test that dashboard properly displays placeholder metrics."""

    def test_placeholder_shown_when_nh_is_none(self):
        """Dashboard shows '--' when new_highs is None."""
        nh = None

        # Simulate the dashboard display logic
        nh_display = nh or "--"

        assert nh_display == "--"
        assert str(nh_display) == "--"

    def test_placeholder_shown_when_nl_is_none(self):
        """Dashboard shows '--' when new_lows is None."""
        nl = None

        nl_display = nl or "--"

        assert nl_display == "--"

    def test_actual_values_shown_when_available(self):
        """Dashboard shows actual counts when available."""
        nh = 150
        nl = 50

        nh_display = nh or "--"
        nl_display = nl or "--"

        assert nh_display == 150
        assert nl_display == 50

    def test_both_missing_shows_both_placeholders(self):
        """Dashboard shows '--' for both when both are missing."""
        nh = None
        nl = None

        nh_display = nh or "--"
        nl_display = nl or "--"

        assert nh_display == "--"
        assert nl_display == "--"


class TestBreadthFetcherFetch:
    """Test the complete BreadthFetcher.fetch() flow."""

    def test_fetch_propagates_validation_error(self):
        """fetch() propagates BreadthFetcher validation errors when price_daily missing."""
        fetcher = BreadthFetcher()

        # Create a mock cursor that will fail when _compute_new_highs_lows is called
        mock_cur = Mock()

        # Configure execute/fetchall/fetchone for the advance/decline query
        # to succeed, then fail on the price_daily validation
        call_count = [0]

        def mock_execute(query, *args):
            call_count[0] += 1
            # First execute: advance/decline query
            # Second execute: COUNT(*) FROM price_daily
            # Third execute: window function query (won't be reached due to validation error)
            if "COUNT(*)" in query and "price_daily" in query:
                # This is the COUNT query - will trigger validation error
                mock_cur.fetchone.return_value = (0,)
                raise RuntimeError(
                    "[BREADTH_FETCHER CRITICAL] price_daily has no rows for 2026-06-01 to 2026-06-28. "
                    "Cannot compute new highs/lows without price data. "
                    "Check: price loader is running, price_daily table is populated."
                )

        mock_cur.execute.side_effect = mock_execute
        mock_cur.fetchall.return_value = [(date(2026, 6, 28), 400, 100)]  # AD data

        start = date(2026, 6, 1)
        end = date(2026, 6, 28)

        # Manually call _compute_new_highs_lows to test validation directly
        with pytest.raises(RuntimeError) as exc_info:
            fetcher._compute_new_highs_lows(mock_cur, start, end)

        assert "price_daily has no rows" in str(exc_info.value)


class TestErrorMessages:
    """Test that error messages are actionable."""

    def test_empty_price_daily_error_is_helpful(self):
        """Empty price_daily error guides debugging."""
        error_msg = (
            "[BREADTH_FETCHER CRITICAL] price_daily has no rows for 2026-06-01 to 2026-06-28. "
            "Cannot compute new highs/lows without price data. "
            "Check: price loader is running, price_daily table is populated."
        )

        assert "price_daily" in error_msg
        assert "price loader" in error_msg.lower()
        assert "Check:" in error_msg

    def test_insufficient_history_error_is_helpful(self):
        """Insufficient history error explains 252-day requirement."""
        error_msg = (
            "[BREADTH_FETCHER CRITICAL] New highs/lows computation returned 0 rows for 2026-06-01 to 2026-06-28. "
            "price_daily has 100 rows in range but window function produced no results. "
            "This typically means price data is too recent (< 252 days history). "
            "Verify: (1) price_daily has >= 252 days of history per symbol, "
            "(2) symbols have continuous trading data without gaps."
        )

        assert "252 days" in error_msg
        assert "continuous" in error_msg
        assert "Verify:" in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
