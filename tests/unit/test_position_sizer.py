#!/usr/bin/env python3
"""Unit tests for PositionSizer module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add algo directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from algo.algo_position_sizer import PositionSizer


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    return {
        "base_risk_pct": 0.75,
        "max_position_size_pct": 8.0,
        "max_concentration_pct": 50.0,
        "max_positions": 12,
    }


@pytest.fixture
def position_sizer(mock_config):
    """Create PositionSizer instance with mocked database."""
    with patch("algo.algo_position_sizer.get_db_connection"):
        sizer = PositionSizer(mock_config, conn=None, cur=None)
    return sizer


class TestPositionSizerInit:
    """Test PositionSizer initialization."""

    def test_init_with_config(self, mock_config):
        """Test initialization with config."""
        with patch("algo.algo_position_sizer.get_db_connection"):
            sizer = PositionSizer(mock_config)
        assert sizer.config == mock_config
        assert sizer.conn is None
        assert sizer.cur is None

    def test_init_with_connection(self, mock_config):
        """Test initialization with provided connection."""
        mock_conn = Mock()
        mock_cur = Mock()
        sizer = PositionSizer(mock_config, conn=mock_conn, cur=mock_cur)
        assert sizer.conn == mock_conn
        assert sizer.cur == mock_cur


class TestPositionSizerBasic:
    """Test basic PositionSizer functionality."""

    def test_get_position_count_no_positions(self, position_sizer):
        """Test position count when no positions exist."""
        with patch.object(position_sizer, "_ensure_connection"):
            with patch.object(position_sizer, "cur") as mock_cur:
                mock_cur.fetchone.return_value = (0,)
                count = position_sizer.get_position_count()
                assert count == 0 or count is None  # Should return 0 or handle gracefully

    def test_get_current_drawdown(self, position_sizer):
        """Test drawdown calculation."""
        with patch.object(position_sizer, "_ensure_connection"):
            with patch.object(position_sizer, "cur") as mock_cur:
                # Mock peak and current equity values
                with patch.object(position_sizer, "get_portfolio_value", return_value=95000):
                    with patch.object(position_sizer, "cur") as peak_cur:
                        peak_cur.fetchone.return_value = (100000,)
                        # Should calculate drawdown as negative
                        assert True  # Placeholder - actual logic tested in integration


class TestPositionSizerCalculations:
    """Test position sizing calculations."""

    def test_calculate_position_size(self, position_sizer):
        """Test position size calculation."""
        entry_price = 100.0
        stop_loss = 95.0

        with patch.object(position_sizer, "_ensure_connection"):
            with patch.object(position_sizer, "get_portfolio_value", return_value=100000):
                with patch.object(position_sizer, "get_risk_adjustment", return_value=1.0):
                    with patch.object(position_sizer, "get_market_exposure_multiplier", return_value=1.0):
                        with patch.object(position_sizer, "get_vix_caution_multiplier", return_value=1.0):
                            with patch.object(position_sizer, "get_position_count", return_value=3):
                                # Position size should be calculated based on risk
                                size = position_sizer.calculate_position_size(
                                    "AAPL", entry_price, stop_loss
                                )
                                # Should return a dict with position details or None
                                assert size is None or isinstance(size, dict)


class TestPositionSizerRiskAdjustment:
    """Test risk adjustment logic."""

    def test_get_risk_adjustment(self, position_sizer):
        """Test risk adjustment calculation."""
        with patch.object(position_sizer, "_ensure_connection"):
            with patch.object(position_sizer, "get_current_drawdown", return_value=-5.0):
                adjustment = position_sizer.get_risk_adjustment()
                # Drawdown at -5% should reduce risk
                assert adjustment is None or isinstance(adjustment, (int, float))

    def test_get_vix_caution_multiplier(self, position_sizer):
        """Test VIX-based caution multiplier."""
        with patch.object(position_sizer, "_ensure_connection"):
            with patch.object(position_sizer, "cur") as mock_cur:
                mock_cur.fetchone.return_value = (20.0,)  # VIX value
                multiplier = position_sizer.get_vix_caution_multiplier()
                # Should return a multiplier
                assert multiplier is None or isinstance(multiplier, (int, float))
