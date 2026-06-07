#!/usr/bin/env python3
"""Tests for ISSUE #7: Grace Period Auto-Tuning"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from algo.orchestrator.phase1_data_freshness import (
    _get_table_names_for_loader,
    _calculate_optimal_grace_period,
)


class TestTableNameMapping:
    """Test mapping of loader names to table names."""

    def test_stock_prices_daily_mapping(self):
        """stock_prices_daily maps to multiple price tables."""
        tables = _get_table_names_for_loader('stock_prices_daily')
        assert 'price_daily' in tables
        assert len(tables) > 1

    def test_single_table_loader(self):
        """Loaders with single table."""
        tables = _get_table_names_for_loader('buy_sell_daily')
        assert 'buy_sell_daily' in tables

    def test_unknown_loader_fallback(self):
        """Unknown loader falls back to common patterns."""
        tables = _get_table_names_for_loader('unknown_loader_daily')
        assert 'unknown_loader_daily' in tables
        assert 'unknown_loader' in tables


class TestGracePeriodAutoCalculation:
    """Test grace period auto-calculation from historical data."""

    @patch('utils.database_context.DatabaseContext')
    def test_sufficient_historical_data(self, mock_db):
        """Auto-calculate when sufficient data available."""
        # Mock database context
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.__exit__.return_value = None

        # Simulate cache miss
        mock_cursor.fetchone.side_effect = [
            None,  # Cache check returns no cached value
            # Execution times query
            (220,), (230,), (240,), (250,), (260,), (270,), (280,), (290,), (300,), (310,),
        ]

        # Mock execute to track calls
        call_count = [0]
        original_execute = mock_cursor.execute

        def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            return original_execute(*args, **kwargs)

        mock_cursor.execute = execute_side_effect

        # Test auto-calculation
        result = _calculate_optimal_grace_period('test_loader_daily', verbose=True)

        # Should calculate from 95th percentile + 30 min safety margin
        # 95th percentile of [220-310] is around 305
        # So grace = min(305+30, 390) = 335
        assert result is not None
        assert 300 <= result <= 390  # Should be in reasonable range

    @patch('utils.database_context.DatabaseContext')
    def test_insufficient_data_returns_none(self, mock_db):
        """Returns None if fewer than 5 samples."""
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.__exit__.return_value = None

        # Simulate cache miss and insufficient data
        mock_cursor.fetchone.side_effect = [
            None,  # Cache check
            # Only 3 execution times
            (220,), (230,), (240,),
        ]

        result = _calculate_optimal_grace_period('test_loader_daily', verbose=True)

        # Should return None (falls back to config/default)
        assert result is None

    @patch('utils.database_context.DatabaseContext')
    def test_respects_hard_cap(self, mock_db):
        """Never exceeds 390 minute hard cap."""
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.__exit__.return_value = None

        # Simulate cache miss and very long execution times
        mock_cursor.fetchone.side_effect = [
            None,  # Cache check
            # Very long execution times
            (300,), (310,), (320,), (330,), (340,), (350,), (360,), (370,), (380,), (390,),
        ]

        result = _calculate_optimal_grace_period('slow_loader', verbose=True)

        # Should cap at 390 even with longer times
        assert result is not None
        assert result <= 390

    @patch('utils.database_context.DatabaseContext')
    def test_respects_minimum(self, mock_db):
        """Never goes below 180 minute minimum."""
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.__exit__.return_value = None

        # Simulate cache miss and very short execution times
        mock_cursor.fetchone.side_effect = [
            None,  # Cache check
            # Very short execution times
            (10,), (15,), (20,), (25,), (30,), (35,), (40,), (45,), (50,), (100,),
        ]

        result = _calculate_optimal_grace_period('fast_loader', verbose=True)

        # Should enforce minimum of 180
        assert result is not None
        assert result >= 180

    @patch('utils.database_context.DatabaseContext')
    def test_cache_hits(self, mock_db):
        """Returns None when fresh cache exists (will use config value)."""
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.__exit__.return_value = None

        # Simulate fresh cached value
        mock_cursor.fetchone.return_value = ('275', 12.5)  # value, age_hours

        result = _calculate_optimal_grace_period('cached_loader', verbose=True)

        # Should return None (use cached value from config)
        assert result is None

    @patch('utils.database_context.DatabaseContext')
    def test_percentile_calculation(self, mock_db):
        """Verify 95th percentile calculation."""
        mock_cursor = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_cursor
        mock_db.return_value.__exit__.return_value = None

        # Simulate cache miss and known execution times
        # Execution times: [100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200]
        # 95th percentile is approximately 190
        execution_times = [
            (100,), (110,), (120,), (130,), (140,),
            (150,), (160,), (170,), (180,), (190,), (200,),
        ]
        mock_cursor.fetchone.side_effect = [
            None,  # Cache check
        ] + execution_times

        result = _calculate_optimal_grace_period('test_loader', verbose=True)

        # 95th percentile ~= 190, + 30 safety margin = 220
        assert result is not None
        assert 200 <= result <= 250  # Should be in the expected range


class TestGracePeriodIntegration:
    """Integration tests for grace period logic."""

    @patch('algo.orchestrator.phase1_data_freshness._calculate_optimal_grace_period')
    def test_check_uses_auto_calculation_first(self, mock_auto_calc):
        """Grace period check should try auto-calculation first."""
        from algo.orchestrator.phase1_data_freshness import _check_failsafe_grace_period
        import time

        mock_auto_calc.return_value = 250  # Auto-calculated value
        mock_state_table = MagicMock()

        now = time.time()
        mock_state_table.get_item.return_value = {
            'Item': {
                'triggered_at': now - 100 * 60,  # 100 minutes ago
                'actual_running_at': now - 100 * 60,
            }
        }

        with patch('utils.database_context.DatabaseContext'):
            # Patch the database context to avoid actual DB calls
            result = _check_failsafe_grace_period(
                mock_state_table,
                verbose=False,
                loader_name='test_loader'
            )

        # Should have called auto-calculation
        mock_auto_calc.assert_called()
        # Should return age_minutes since within 250-min grace period
        assert result is not None
        assert 95 < result < 105


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
