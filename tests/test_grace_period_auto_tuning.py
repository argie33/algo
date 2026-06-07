#!/usr/bin/env python3
"""Tests for ISSUE #7: Grace Period Auto-Tuning"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

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

    @patch('algo.orchestrator.phase1_data_freshness.DatabaseContext')
    def test_sufficient_historical_data(self, mock_db_class):
        """Auto-calculate when sufficient data available."""
        mock_cursor = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_cursor
        mock_context.__exit__.return_value = None
        mock_db_class.return_value = mock_context

        mock_cursor.fetchall.return_value = [(220,), (230,), (240,), (250,), (260,), (270,), (280,), (290,), (300,), (310,)]
        mock_cursor.fetchone.return_value = None

        result = _calculate_optimal_grace_period('test_loader_daily', verbose=False)

        assert result is not None
        assert 300 <= result <= 390

    @patch('algo.orchestrator.phase1_data_freshness.DatabaseContext')
    def test_insufficient_data_returns_none(self, mock_db_class):
        """Returns None if fewer than 5 samples across all tables."""
        mock_cursor = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_cursor
        mock_context.__exit__.return_value = None
        mock_db_class.return_value = mock_context

        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None

        result = _calculate_optimal_grace_period('test_loader_daily', verbose=False)

        assert result is None

    @patch('algo.orchestrator.phase1_data_freshness.DatabaseContext')
    def test_respects_hard_cap(self, mock_db_class):
        """Never exceeds 390 minute hard cap."""
        mock_cursor = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_cursor
        mock_context.__exit__.return_value = None
        mock_db_class.return_value = mock_context

        mock_cursor.fetchall.return_value = [(300,), (310,), (320,), (330,), (340,), (350,), (360,), (370,), (380,), (390,)]
        mock_cursor.fetchone.return_value = None

        result = _calculate_optimal_grace_period('slow_loader', verbose=False)

        assert result is not None
        assert result <= 390

    @patch('algo.orchestrator.phase1_data_freshness.DatabaseContext')
    def test_respects_minimum(self, mock_db_class):
        """Never goes below 180 minute minimum."""
        mock_cursor = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_cursor
        mock_context.__exit__.return_value = None
        mock_db_class.return_value = mock_context

        mock_cursor.fetchall.return_value = [(10,), (15,), (20,), (25,), (30,), (35,), (40,), (45,), (50,), (100,)]
        mock_cursor.fetchone.return_value = None

        result = _calculate_optimal_grace_period('fast_loader', verbose=False)

        assert result is not None
        assert result >= 180

    @patch('algo.orchestrator.phase1_data_freshness.DatabaseContext')
    def test_cache_hits(self, mock_db_class):
        """Returns None when fresh cache exists (will use config value)."""
        mock_cursor = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_cursor
        mock_context.__exit__.return_value = None
        mock_db_class.return_value = mock_context

        mock_cursor.fetchone.return_value = ('275', 12.5)

        result = _calculate_optimal_grace_period('cached_loader', verbose=False)

        assert result is None

    @patch('algo.orchestrator.phase1_data_freshness.DatabaseContext')
    def test_percentile_calculation(self, mock_db_class):
        """Verify 95th percentile calculation."""
        mock_cursor = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_cursor
        mock_context.__exit__.return_value = None
        mock_db_class.return_value = mock_context

        times = [(100,), (110,), (120,), (130,), (140,), (150,), (160,), (170,), (180,), (190,), (200,)]
        mock_cursor.fetchall.return_value = times
        mock_cursor.fetchone.return_value = None

        result = _calculate_optimal_grace_period('test_loader', verbose=False)

        assert result is not None
        assert 200 <= result <= 250
