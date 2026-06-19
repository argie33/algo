#!/usr/bin/env python3
"""Unit tests for PositionSizer module."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


# Add algo directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from algo.trading import PositionSizer


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    return {
        "base_risk_pct": 0.75,
        "max_position_size_pct": 8.0,
        "max_concentration_pct": 50.0,
        "max_positions": 12,
        "risk_reduction_at_minus_5": 0.75,
        "risk_reduction_at_minus_10": 0.5,
        "risk_reduction_at_minus_15": 0.25,
        "vix_caution_threshold": 25.0,
        "vix_max_threshold": 35.0,
        "vix_caution_risk_reduction": 0.75,
    }


@pytest.fixture
def position_sizer(mock_config):
    """Create PositionSizer instance with mocked database."""
    with patch("algo.trading.position_sizer.DatabaseContext"):
        return PositionSizer(mock_config)


class TestPositionSizerInit:
    """Test PositionSizer initialization."""

    def test_init_with_config(self, mock_config):
        """Test initialization with config."""
        sizer = PositionSizer(mock_config)
        assert sizer.config == mock_config

    def test_init_with_connection(self, mock_config):
        """Test initialization creates instance."""
        sizer = PositionSizer(mock_config)
        assert sizer.config == mock_config


class TestPositionSizerBasic:
    """Test basic PositionSizer functionality."""

    def test_get_current_drawdown_no_snapshots(self, position_sizer):
        """Test drawdown calculation when no snapshots exist."""

        def mock_cursor_op(operation):
            mock_cur = Mock()
            mock_cur.fetchone.return_value = (0,)  # Count of snapshots
            return operation(mock_cur)

        with patch.object(position_sizer, "_with_cursor", side_effect=mock_cursor_op):
            with pytest.raises(RuntimeError, match="No portfolio snapshots found"):
                position_sizer.get_current_drawdown()

    def test_get_current_drawdown_with_snapshots(self, position_sizer):
        """Test drawdown calculation with portfolio snapshots."""

        def mock_cursor_op(operation):
            mock_cur = Mock()
            execute_calls = []

            def mock_execute(query):
                execute_calls.append(query)

            def mock_fetchone():
                if execute_calls and "COUNT(*)" in execute_calls[-1]:
                    return (10,)  # 10 snapshots exist
                else:
                    return (100000.0, 95000.0)  # peak, current

            mock_cur.execute = mock_execute
            mock_cur.fetchone = mock_fetchone
            return operation(mock_cur)

        with patch.object(position_sizer, "_with_cursor", side_effect=mock_cursor_op):
            drawdown = position_sizer.get_current_drawdown()
            assert drawdown == 5.0


class TestPositionSizerCalculations:
    """Test position sizing calculations."""

    def test_risk_adjustment_normal_conditions(self, position_sizer):
        """Test risk adjustment with no drawdown."""
        with patch.object(position_sizer, "get_current_drawdown", return_value=0.0):
            adjustment = position_sizer.get_risk_adjustment()
            assert adjustment == 1.0

    def test_risk_adjustment_drawdown_5_percent(self, position_sizer):
        """Test risk adjustment at -5% drawdown."""
        with patch.object(position_sizer, "get_current_drawdown", return_value=5.0):
            adjustment = position_sizer.get_risk_adjustment()
            assert adjustment == 0.75

    def test_risk_adjustment_drawdown_20_percent(self, position_sizer):
        """Test risk adjustment at -20% drawdown (halts trading)."""
        with patch.object(position_sizer, "get_current_drawdown", return_value=20.0):
            adjustment = position_sizer.get_risk_adjustment()
            assert adjustment == 0.0


class TestPositionSizerVIX:
    """Test VIX-based multiplier logic."""

    def test_get_vix_caution_multiplier_low_vix(self, position_sizer):
        """Test VIX multiplier when VIX is low (no caution)."""

        def mock_cursor_op(operation):
            mock_cur = Mock()
            mock_cur.fetchone.return_value = (
                15.0,
            )  # VIX value below caution threshold
            return operation(mock_cur)

        with patch.object(position_sizer, "_with_cursor", side_effect=mock_cursor_op):
            multiplier = position_sizer.get_vix_caution_multiplier()
            assert multiplier == 1.0

    def test_get_vix_caution_multiplier_caution_zone(self, position_sizer):
        """Test VIX multiplier when VIX is in caution zone."""

        def mock_cursor_op(operation):
            mock_cur = Mock()
            mock_cur.fetchone.return_value = (30.0,)  # VIX in caution zone (25-35)
            return operation(mock_cur)

        with patch.object(position_sizer, "_with_cursor", side_effect=mock_cursor_op):
            multiplier = position_sizer.get_vix_caution_multiplier()
            assert multiplier == 0.75
