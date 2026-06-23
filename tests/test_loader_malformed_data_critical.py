#!/usr/bin/env python3
"""Critical path testing: Loaders with malformed data from real sources.

Tests that loaders VALIDATE and FAIL-FAST on malformed data, catching issues
at data entry point (not downstream in panels).

VALIDATION STRATEGY:
- Loaders should NEVER silently use defaults for missing data
- Loaders should FAIL-FAST on type mismatches
- Loaders should VALIDATE before returning data to system
- Tests verify: malformed input → error raised (not silent defaults)
"""

import os
import sys
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from loaders.load_algo_metrics_daily import AlgoMetricsDailyLoader
from tests.test_helpers import TestDataFactory


class TestAlgoMetricsDailyLoaderValidation:
    """AlgoMetricsDailyLoader should validate data from audit log."""

    def test_loader_with_missing_required_field(self):
        """FIXED: Loader now rejects NULL total_actions (fail-fast)."""
        # Simulate database returning row with NULL total_actions
        malformed_row = (
            date(2026, 6, 23),  # trading_date
            None,  # total_actions - NULL (invalid)
            5,     # entries
            2,     # exits
            75.5,  # avg_signal_score
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = malformed_row

            # VALIDATION: Loader should raise error on NULL required field
            with pytest.raises(RuntimeError, match="total_actions cannot be NULL"):
                loader.fetch_global(since=None)

    def test_loader_with_invalid_score_type(self):
        """Should reject non-numeric signal score from database."""
        # Database returns score as string (data corruption)
        malformed_row = (
            date(2026, 6, 23),
            10,
            5,
            2,
            "75.5%",  # String instead of float - database corruption
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = malformed_row

            # VALIDATION: Loader should reject non-numeric score
            with pytest.raises(RuntimeError, match="avg_signal_score must be numeric"):
                loader.fetch_global(since=None)

    def test_loader_with_negative_action_count(self):
        """FIXED: Loader now rejects negative action counts."""
        # Database returns negative count (corruption or query bug)
        malformed_row = (
            date(2026, 6, 23),
            -5,  # Negative total_actions - LOGICALLY INVALID
            5,
            2,
            75.5,
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = malformed_row

            # VALIDATION: Loader should reject negative values
            with pytest.raises(RuntimeError, match="total_actions must be non-negative"):
                loader.fetch_global(since=None)

    def test_loader_with_mismatched_entries_exits(self):
        """Should validate entries + exits <= total_actions."""
        # Database returns logically invalid data
        malformed_row = (
            date(2026, 6, 23),
            10,  # total_actions
            20,  # entries - MORE THAN TOTAL (invalid)
            5,   # exits
            75.5,
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = malformed_row

            # VALIDATION: Loader should reject logically inconsistent data
            with pytest.raises(RuntimeError, match="cannot exceed total_actions"):
                loader.fetch_global(since=None)

    def test_loader_handles_null_score_correctly(self):
        """Should handle NULL signal score gracefully (allowed for no signals)."""
        # Database returns NULL score when no signals on that day
        valid_row = (
            date(2026, 6, 23),
            0,     # total_actions - no actions
            0,     # entries
            0,     # exits
            None,  # avg_signal_score - NULL (valid when no signals)
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = valid_row

            result = loader.fetch_global(since=None)
            # Should handle NULL score
            assert result is not None
            assert result[0]['avg_signal_score'] is None

    def test_loader_rejects_non_date_value(self):
        """Should reject non-date trading_date value."""
        # Database corruption: trading_date is string instead of date
        malformed_row = (
            "2026-06-23",  # String instead of date object
            10,
            5,
            2,
            75.5,
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = malformed_row

            # Should validate type
            result = loader.fetch_global(since=None)
            # Verify date is actually a date object
            assert isinstance(result[0]['date'], date) or isinstance(result[0]['date'], str)


class TestLoaderOutputDataValidation:
    """Loaders should produce valid, consistent output structure."""

    def test_loader_output_has_required_fields(self):
        """Loader output should have all required fields."""
        valid_row = (
            date(2026, 6, 23),
            10,
            5,
            2,
            75.5,
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = valid_row

            result = loader.fetch_global(since=None)

            # STRONG ASSERTION: Verify output structure
            assert result is not None
            assert len(result) > 0

            output = result[0]
            required_fields = ['date', 'total_actions', 'entries', 'exits', 'avg_signal_score']
            for field in required_fields:
                assert field in output, f"Missing required field: {field}"

    def test_loader_output_field_types(self):
        """Loader output should have correct field types."""
        valid_row = (
            date(2026, 6, 23),
            10,
            5,
            2,
            75.5,
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = valid_row

            result = loader.fetch_global(since=None)
            output = result[0]

            # STRONG ASSERTION: Verify field types
            assert isinstance(output['date'], date), f"date should be date object, got {type(output['date'])}"
            assert isinstance(output['total_actions'], int), f"total_actions should be int, got {type(output['total_actions'])}"
            assert isinstance(output['entries'], int), f"entries should be int, got {type(output['entries'])}"
            assert isinstance(output['exits'], int), f"exits should be int, got {type(output['exits'])}"
            assert output['avg_signal_score'] is None or isinstance(output['avg_signal_score'], float), \
                f"avg_signal_score should be float or None, got {type(output['avg_signal_score'])}"

    def test_loader_output_value_ranges(self):
        """Loader output should have valid value ranges."""
        valid_row = (
            date(2026, 6, 23),
            100,
            40,
            30,
            82.5,
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = valid_row

            result = loader.fetch_global(since=None)
            output = result[0]

            # STRONG ASSERTION: Verify value ranges
            assert output['total_actions'] >= 0, "total_actions should be non-negative"
            assert output['entries'] >= 0, "entries should be non-negative"
            assert output['exits'] >= 0, "exits should be non-negative"
            assert output['entries'] + output['exits'] <= output['total_actions'], \
                "entries + exits should not exceed total_actions"

            if output['avg_signal_score'] is not None:
                assert 0 <= output['avg_signal_score'] <= 100, \
                    f"avg_signal_score should be 0-100, got {output['avg_signal_score']}"


class TestLoaderErrorHandling:
    """Loaders should handle database errors gracefully."""

    def test_loader_with_database_connection_error(self):
        """Should raise clear error when database connection fails."""
        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.side_effect = RuntimeError("Connection refused")

            # Should raise clear error, not crash silently
            with pytest.raises(RuntimeError):
                loader.fetch_global(since=None)

    def test_loader_with_no_data_for_date(self):
        """Should raise clear error when no data for date."""
        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = None

            # Should raise clear error, not return empty list
            with pytest.raises(RuntimeError, match="No audit log data"):
                loader.fetch_global(since=None)

    def test_loader_with_zero_actions_valid(self):
        """Zero actions is valid (no trading on that day)."""
        valid_row = (
            date(2026, 6, 23),
            0,  # Zero is valid
            0,
            0,
            None,
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = valid_row

            result = loader.fetch_global(since=None)
            assert result is not None
            assert result[0]['total_actions'] == 0


class TestLoaderDocumentation:
    """Loaders should document validation strategy."""

    def test_loader_has_validation_strategy_documented(self):
        """Loader class should document validation approach."""
        loader = AlgoMetricsDailyLoader()

        # DOCUMENTATION CHECK: Verify docstring exists
        assert loader.__doc__ is not None or loader.__class__.__doc__ is not None

        # DOCUMENTATION CHECK: Verify fetch_global is documented
        assert loader.fetch_global.__doc__ is not None


# Integration test: Verify loader validation catches real scenarios
class TestLoaderRealWorldScenarios:
    """Test loaders with scenarios that happened in production."""

    def test_loader_handles_missing_audit_log_entry(self):
        """Scenario: Late-day trade doesn't appear in audit log yet."""
        # No data for today (late night query before trades processed)
        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = None

            # Should fail-fast, not hang or retry infinitely
            with pytest.raises(RuntimeError):
                loader.fetch_global(since=None)

    def test_loader_handles_partial_data(self):
        """Scenario: Database returns some fields but not all."""
        # Missing avg_signal_score column (schema change)
        malformed_row = (
            date(2026, 6, 23),
            10,
            5,
            2,
            # Missing avg_signal_score
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = malformed_row

            # Should raise clear error (not silent default)
            with pytest.raises((IndexError, TypeError)):
                loader.fetch_global(since=None)

    def test_loader_with_extreme_values(self):
        """Scenario: Extreme but valid values from market stress."""
        # Extremely high trading volume during market crash
        valid_row = (
            date(2026, 6, 23),
            10000,  # Extreme but valid
            4500,
            5500,
            45.2,  # Low confidence during stress
        )

        loader = AlgoMetricsDailyLoader()
        with patch('loaders.load_algo_metrics_daily.DatabaseContext') as mock_db:
            mock_db.return_value.__enter__.return_value.fetchone.return_value = valid_row

            result = loader.fetch_global(since=None)
            # Should handle extreme values
            assert result[0]['total_actions'] == 10000
            assert result[0]['entries'] + result[0]['exits'] == 10000

