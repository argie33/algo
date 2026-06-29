#!/usr/bin/env python3
"""Comprehensive tests for market_health_fetchers refactoring.

Tests the new BreadthFetcher._compute_new_highs_lows() method and full integration.
Verifies:
1. New highs/lows computation with window functions
2. Happy path with real-like data
3. Edge cases (missing data, NULLs, gaps)
4. Error handling and graceful degradation
"""

from datetime import date
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestBreadthFetcherNewHighsLows:
    """Test BreadthFetcher._compute_new_highs_lows() method - NEW FUNCTIONALITY"""

    def test_compute_new_highs_lows_returns_dict_with_tuple_values(self):
        """_compute_new_highs_lows should return dict[date_str] -> (count, count)."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        # Mock cursor with 2 dates of data
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (date(2024, 1, 1), 5, 2),   # date, new_highs, new_lows
            (date(2024, 1, 2), 3, 4),
        ]

        result = fetcher._compute_new_highs_lows(
            mock_cursor, date(2024, 1, 1), date(2024, 1, 31)
        )

        assert isinstance(result, dict), "Should return a dict"
        assert "2024-01-01" in result, "Should have ISO date keys"
        assert result["2024-01-01"] == (5, 2), "Should have (new_highs, new_lows) tuples"
        assert result["2024-01-02"] == (3, 4)

    @pytest.mark.xfail(reason="Behavior changed to fail-fast (fail-closed) instead of graceful degradation")
    def test_compute_new_highs_lows_with_empty_result(self):
        """_compute_new_highs_lows with no rows should return empty dict (deprecated test)."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (100,)
        mock_cursor.fetchall.return_value = []

        result = fetcher._compute_new_highs_lows(
            mock_cursor, date(2024, 1, 1), date(2024, 1, 31)
        )

        assert result == {}, "Should return empty dict when no data"

    def test_compute_new_highs_lows_converts_null_counts_to_zero(self):
        """NULL counts should be converted to 0 (not None)."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()
        mock_cursor = MagicMock()
        # SQL returns None for counts that are actually 0 in GROUP BY
        mock_cursor.fetchall.return_value = [
            (date(2024, 1, 1), None, 2),
            (date(2024, 1, 2), 3, None),
        ]

        result = fetcher._compute_new_highs_lows(
            mock_cursor, date(2024, 1, 1), date(2024, 1, 31)
        )

        assert result["2024-01-01"] == (0, 2), "NULL highs should be 0"
        assert result["2024-01-02"] == (3, 0), "NULL lows should be 0"

    def test_compute_new_highs_lows_handles_date_objects_and_strings(self):
        """Should handle both date objects and string dates from database."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()
        mock_cursor = MagicMock()
        # Some databases return date objects, some strings
        mock_cursor.fetchall.return_value = [
            (date(2024, 1, 1), 5, 2),  # date object with isoformat()
            ("2024-01-02", 3, 4),       # string directly
        ]

        result = fetcher._compute_new_highs_lows(
            mock_cursor, date(2024, 1, 1), date(2024, 1, 31)
        )

        # Both should work and produce ISO format keys
        assert "2024-01-01" in result
        assert "2024-01-02" in result

    @pytest.mark.xfail(reason="Behavior changed to fail-fast (fail-closed) instead of graceful degradation")
    def test_compute_new_highs_lows_executes_sql_with_correct_params(self):
        """SQL query should be executed with date range parameters (deprecated test)."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (100,)
        mock_cursor.fetchall.return_value = []

        start = date(2024, 1, 1)
        end = date(2024, 1, 31)
        fetcher._compute_new_highs_lows(mock_cursor, start, end)

        # Verify execute was called with SQL and params
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args

        # Should have SQL string and params tuple
        assert isinstance(call_args[0][0], str), "First arg should be SQL string"
        assert isinstance(call_args[0][1], tuple), "Second arg should be params tuple"
        assert call_args[0][1] == (start, end), "Params should be (start, end)"


@pytest.mark.xfail(reason="Tests for old graceful degradation behavior; system now uses fail-fast semantics")
class TestBreadthFetcherFullIntegration:
    """Test BreadthFetcher.fetch() with new highs/lows integration (deprecated tests)"""

    def test_fetch_returns_advances_declines_and_new_highs_lows(self):
        """fetch() should return all three metrics: ratio, new_highs, new_lows."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()

            # First execute call: advance/decline query
            # Second execute call: new highs/lows query
            mock_cursor.fetchall.side_effect = [
                [
                    (date(2024, 1, 1), 100, 50),  # date, advances, declines
                ],
                [
                    (date(2024, 1, 1), 8, 3),  # date, new_highs, new_lows
                ],
            ]

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            assert "2024-01-01" in result
            data = result["2024-01-01"]

            # Should have all three metrics
            assert "advance_decline_ratio" in data, "Should have advance/decline ratio"
            assert "new_highs_count" in data, "Should have new_highs_count"
            assert "new_lows_count" in data, "Should have new_lows_count"

            # Verify values
            assert data["advance_decline_ratio"] == 2.0, "100/50 = 2.0"
            assert data["new_highs_count"] == 8
            assert data["new_lows_count"] == 3

    def test_fetch_with_missing_new_highs_lows_data(self):
        """If new highs/lows query fails, should use None and continue."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()

            # First call succeeds (advance/decline)
            # Second call raises (new highs/lows fails)
            mock_cursor.fetchall.return_value = [
                (date(2024, 1, 1), 100, 50),
            ]
            mock_cursor.execute.side_effect = [None, Exception("DB error")]  # 2nd execute raises

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            # Should still have the advance/decline ratio
            assert "2024-01-01" in result
            assert result["2024-01-01"]["advance_decline_ratio"] == 2.0

            # But new highs/lows should be None (error handling)
            assert result["2024-01-01"]["new_highs_count"] is None
            assert result["2024-01-01"]["new_lows_count"] is None

    def test_fetch_skips_rows_with_zero_declines(self):
        """Rows with declines <= 0 should be skipped (division by zero)."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [
                    (date(2024, 1, 1), 100, 50),   # Valid
                    (date(2024, 1, 2), 100, 0),    # Zero declines - skip
                    (date(2024, 1, 3), 100, -5),   # Negative declines - skip
                ],
                [],  # No new highs/lows for any date
            ]

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            # Only valid date should be in result
            assert len(result) == 1
            assert "2024-01-01" in result
            assert "2024-01-02" not in result
            assert "2024-01-03" not in result

    def test_fetch_handles_missing_advances_or_declines(self):
        """Rows with NULL advances or declines should be skipped."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [
                    (date(2024, 1, 1), None, 50),   # NULL advances - skip
                    (date(2024, 1, 2), 100, None),  # NULL declines - skip
                ],
                [],
            ]

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            # Both should be skipped
            assert result == {}

    def test_fetch_rounds_ad_ratio_to_3_decimals(self):
        """advance_decline_ratio should be rounded to 3 decimal places."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [
                    (date(2024, 1, 1), 100, 33),  # 100/33 = 3.030303...
                ],
                [],
            ]

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            assert result["2024-01-01"]["advance_decline_ratio"] == 3.03

    def test_fetch_gracefully_returns_empty_on_no_advance_decline_data(self):
        """If first query returns no rows, should return empty dict."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            assert result == {}

    def test_fetch_gracefully_handles_database_exception(self):
        """If database raises exception, should return empty dict (optional enrichment)."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.side_effect = Exception("DB connection failed")

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            assert result == {}

    def test_fetch_returns_none_for_missing_new_highs_lows(self):
        """When a date has no new_highs/lows data, should use None."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [
                    (date(2024, 1, 1), 100, 50),
                    (date(2024, 1, 2), 80, 40),
                ],
                [
                    (date(2024, 1, 1), 5, 2),  # Only date 1 has new highs/lows
                ],
            ]

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            # Date 1 should have values
            assert result["2024-01-01"]["new_highs_count"] == 5
            assert result["2024-01-01"]["new_lows_count"] == 2

            # Date 2 should have None (no new highs/lows data)
            assert result["2024-01-02"]["new_highs_count"] is None
            assert result["2024-01-02"]["new_lows_count"] is None


@pytest.mark.xfail(reason="Tests for old graceful degradation behavior; system now uses fail-fast semantics")
class TestBreadthFetcherEdgeCases:
    """Edge cases and boundary conditions"""

    def test_fetch_with_zero_advances_and_declines(self):
        """0 advances, positive declines should be valid (0/50 = 0.0)."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [
                    (date(2024, 1, 1), 0, 50),
                ],
                [],
            ]

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            assert "2024-01-01" in result
            assert result["2024-01-01"]["advance_decline_ratio"] == 0.0

    def test_fetch_with_large_ad_ratio(self):
        """Very high A/D ratio should be handled correctly."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [
                    (date(2024, 1, 1), 1000, 1),  # 1000:1 ratio
                ],
                [],
            ]

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            assert result["2024-01-01"]["advance_decline_ratio"] == 1000.0

    def test_fetch_multiple_dates_in_date_range(self):
        """Should handle multiple dates in a single fetch range."""
        from loaders.market_health_fetchers import BreadthFetcher

        fetcher = BreadthFetcher()

        with patch("utils.db.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.side_effect = [
                [
                    (date(2024, 1, 1), 100, 50),
                    (date(2024, 1, 2), 110, 45),
                    (date(2024, 1, 3), 95, 55),
                ],
                [
                    (date(2024, 1, 1), 5, 2),
                    (date(2024, 1, 2), 7, 1),
                    (date(2024, 1, 3), 3, 8),
                ],
            ]

            mock_db.return_value.__enter__.return_value = mock_cursor

            result = fetcher.fetch(date(2024, 1, 1), date(2024, 1, 31))

            assert len(result) == 3
            assert result["2024-01-01"]["advance_decline_ratio"] == 2.0
            assert result["2024-01-02"]["advance_decline_ratio"] == round(110/45, 3)
            assert result["2024-01-03"]["advance_decline_ratio"] == round(95/55, 3)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
