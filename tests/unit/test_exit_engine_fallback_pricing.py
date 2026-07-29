#!/usr/bin/env python3
"""Test exit engine fallback pricing for unavailable symbols."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from algo.trading.exit_engine import ExitEngine


@pytest.fixture
def mock_config():
    """Mock configuration for ExitEngine."""
    return {
        "min_hold_days": 1,
        "max_hold_days": 60,
        "eight_week_rule_threshold_pct": 20.0,
        "eight_week_rule_window_days": 21,
        "exit_on_distribution_day": False,
        "max_distribution_days": 3,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
        "execution_mode": "paper",  # Required for ExitEngine init
        "alpaca_paper_trading": True,  # Required for TradeExecutor
    }


def test_fetch_recent_prices_alpaca_404_fallback_today(mock_config):
    """Test that when Alpaca returns 404, we fall back to price_daily."""
    with patch('algo.trading.exit_engine.TradeExecutor'):
        engine = ExitEngine(mock_config)

        # Mock database cursor
        mock_cur = MagicMock()

        # Mock _fetch_alpaca_quote to return None (simulating 404 fallback)
        with patch.object(engine, '_fetch_alpaca_quote', return_value=None):
            # Mock price_daily query to return today's prices
            mock_cur.fetchall.return_value = [
                (date(2026, 7, 21), Decimal('100.50')),  # current price
                (date(2026, 7, 20), Decimal('99.75')),   # previous close
            ]

            current_price, prev_close = engine._fetch_recent_prices(mock_cur, 'TEST', date(2026, 7, 21))

            assert current_price == 100.5
            assert prev_close == 99.75


def test_fetch_recent_prices_no_today_data_fails_fast(mock_config):
    """Test that when today's data is missing, we fail-fast instead of using stale data.

    FAIL-FAST PRINCIPLE: Exit decisions require current market data, not stale historical prices.
    Using stale data masks data availability issues and risks incorrect exit execution.
    """
    with patch('algo.trading.exit_engine.TradeExecutor'):
        engine = ExitEngine(mock_config)

        mock_cur = MagicMock()

        with patch.object(engine, '_fetch_alpaca_quote', return_value=None):
            # No prices available on/before today
            mock_cur.fetchall.return_value = []

            with pytest.raises(RuntimeError) as exc_info:
                engine._fetch_recent_prices(mock_cur, 'ILLIQUID', date(2026, 7, 21))

            # Verify error message explains why we can't fall back
            error_msg = str(exc_info.value)
            assert "current market data required" in error_msg
            assert "fail-fast" in error_msg.lower()


def test_fetch_recent_prices_no_data_at_all_raises(mock_config):
    """Test that RuntimeError is raised when NO price data exists at all."""
    with patch('algo.trading.exit_engine.TradeExecutor'):
        engine = ExitEngine(mock_config)

        mock_cur = MagicMock()

        with patch.object(engine, '_fetch_alpaca_quote', return_value=None):
            # No data available
            mock_cur.fetchall.return_value = []

            with pytest.raises(RuntimeError) as exc_info:
                engine._fetch_recent_prices(mock_cur, 'DELISTED', date(2026, 7, 21))

            error_msg = str(exc_info.value)
            assert "No price data available" in error_msg
            assert "delisted" in error_msg.lower() or "data gap" in error_msg.lower()


def test_fetch_recent_prices_single_price_point_raises(mock_config):
    """Test that we need current data (on/before today), not historical prices.

    Even with price history available, we require data on or before the current date.
    Using old data corrupts exit decisions.
    """
    with patch('algo.trading.exit_engine.TradeExecutor'):
        engine = ExitEngine(mock_config)

        mock_cur = MagicMock()

        with patch.object(engine, '_fetch_alpaca_quote', return_value=None):
            # No prices on/before today (only historical)
            mock_cur.fetchall.return_value = []

            with pytest.raises(RuntimeError) as exc_info:
                engine._fetch_recent_prices(mock_cur, 'NEWSTOCK', date(2026, 7, 21))

            error_msg = str(exc_info.value)
            assert "No price data available on/before" in error_msg or "current market data required" in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
