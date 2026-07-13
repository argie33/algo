#!/usr/bin/env python3
"""Integration tests verifying endpoints handle missing data gracefully.

Tests that the 4 main dashboard endpoints properly return service unavailable
errors (503) rather than internal server errors (500) when database is unavailable
or data doesn't exist.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import psycopg2
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestEndpointsMissingData:
    """Verify endpoints handle missing data / database errors gracefully."""

    @pytest.fixture
    def mock_cursor(self):
        cursor = Mock()
        # Simulate database query error
        cursor.execute.side_effect = psycopg2.OperationalError("connection refused")
        cursor.fetchall.side_effect = psycopg2.OperationalError("connection refused")
        cursor.fetchone.side_effect = psycopg2.OperationalError("connection refused")
        return cursor

    def test_positions_handles_db_error(self, mock_cursor):
        """Positions endpoint should return 503 (not 500) when database unavailable."""
        from routes.algo_handlers.dashboard import _get_algo_positions

        result = _get_algo_positions(mock_cursor)

        # CRITICAL: Must be 503 (Service Unavailable), NOT 500 (Internal Error)
        assert result.get("statusCode") in (503, 504), (
            f"Positions should return 503/504 on DB error, got {result.get('statusCode')}: {result.get('message')}"
        )
        assert result.get("statusCode") != 500, f"Positions returned 500 error: {result.get('message')}"

    def test_trades_handles_db_error(self, mock_cursor):
        """Trades endpoint should return 503 (not 500) when database unavailable."""
        from routes.algo_handlers.dashboard import _get_algo_trades

        result = _get_algo_trades(mock_cursor)

        assert result.get("statusCode") in (503, 504), (
            f"Trades should return 503/504 on DB error, got {result.get('statusCode')}: {result.get('message')}"
        )
        assert result.get("statusCode") != 500, f"Trades returned 500 error: {result.get('message')}"

    def test_circuit_breakers_handles_db_error(self, mock_cursor):
        """Circuit breakers endpoint should return 503 (not 500) when database unavailable."""
        from routes.algo_handlers.dashboard import _get_circuit_breakers

        result = _get_circuit_breakers(mock_cursor)

        assert result.get("statusCode") in (503, 504), (
            f"Circuit breakers should return 503/504 on DB error, got {result.get('statusCode')}: {result.get('message')}"
        )
        assert result.get("statusCode") != 500, f"Circuit breakers returned 500 error: {result.get('message')}"

    def test_dashboard_signals_handles_db_error(self, mock_cursor):
        """Dashboard signals endpoint should return 503 (not 500) when database unavailable."""
        from routes.algo_handlers.dashboard import _get_dashboard_signals

        result = _get_dashboard_signals(mock_cursor)

        assert result.get("statusCode") in (503, 504), (
            f"Dashboard signals should return 503/504 on DB error, got {result.get('statusCode')}: {result.get('message')}"
        )
        assert result.get("statusCode") != 500, f"Dashboard signals returned 500 error: {result.get('message')}"

    def test_empty_data_positions_returns_success(self):
        """Positions endpoint should return 200 with empty array when no data exists."""
        cursor = Mock()
        cursor.execute = Mock()
        cursor.fetchall = Mock(return_value=[])
        cursor.fetchone = Mock(return_value=None)
        cursor.description = None

        with patch("routes.algo_handlers.dashboard.check_data_freshness", return_value={"is_stale": False}):
            from routes.algo_handlers.dashboard import _get_algo_positions

            result = _get_algo_positions(cursor)

            # Should return 200 even with no data
            assert result.get("statusCode") == 200, (
                f"Positions should return 200 with empty data, got {result.get('statusCode')}"
            )
            assert isinstance(result.get("data", {}).get("items"), list), "Positions should return empty items array"
            assert len(result.get("data", {}).get("items", [])) == 0, (
                "Positions should return empty array when no positions"
            )

    def test_empty_data_trades_returns_success(self):
        """Trades endpoint should return 200 with empty array when no trades exist."""
        cursor = Mock()
        cursor.execute = Mock()
        cursor.fetchall = Mock(return_value=[])
        cursor.fetchone = Mock(return_value=None)
        cursor.description = None

        with patch("routes.algo_handlers.dashboard.check_data_freshness", return_value={"is_stale": False}):
            from routes.algo_handlers.dashboard import _get_algo_trades

            result = _get_algo_trades(cursor)

            # Should return 200 even with no data
            assert result.get("statusCode") == 200, (
                f"Trades should return 200 with empty data, got {result.get('statusCode')}"
            )
            assert isinstance(result.get("data", {}).get("items"), list), "Trades should return empty items array"
            assert len(result.get("data", {}).get("items", [])) == 0, "Trades should return empty array when no trades"

    def test_pagination_offset_correct_format(self):
        """Pagination should use 'offset' not 'page' in response."""
        cursor = Mock()
        cursor.execute = Mock()
        cursor.fetchall = Mock(return_value=[])
        cursor.fetchone = Mock(return_value=None)
        cursor.description = None

        with patch("routes.algo_handlers.dashboard.check_data_freshness", return_value={"is_stale": False}):
            from routes.algo_handlers.dashboard import _get_algo_trades

            result = _get_algo_trades(cursor, limit=50)

            # Check pagination structure
            pagination = result.get("data", {}).get("pagination", {})
            assert "offset" in pagination, "Pagination should have 'offset' field"
            assert pagination.get("offset") == 0, "Default offset should be 0"
            assert pagination.get("limit") == 50, "Limit should match request"
            assert "page" not in pagination, "Pagination should NOT have 'page' field (use offset)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
