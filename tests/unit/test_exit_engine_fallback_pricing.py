#!/usr/bin/env python3
"""Test exit engine fallback pricing for unavailable symbols."""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

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


def test_fetch_recent_prices_no_today_data_fallback_historical(mock_config):
    """Test that when today's data is missing, we use most recent available price."""
    with patch('algo.trading.exit_engine.TradeExecutor'):
        engine = ExitEngine(mock_config)

        mock_cur = MagicMock()

        with patch.object(engine, '_fetch_alpaca_quote', return_value=None):
            # First query (looking for data <= today) returns nothing
            # Second query (looking for most recent ANY date) returns historical data
            mock_cur.fetchall.side_effect = [
                [],  # No prices for today or earlier
                [
                    (date(2026, 7, 19), Decimal('98.50')),  # most recent available
                    (date(2026, 7, 18), Decimal('97.75')),
                ]
            ]

            current_price, prev_close = engine._fetch_recent_prices(mock_cur, 'ILLIQUID', date(2026, 7, 21))

            assert current_price == 98.5
            assert prev_close == 97.75


def test_fetch_recent_prices_no_data_at_all_raises(mock_config):
    """Test that RuntimeError is raised when NO price data exists at all."""
    with patch('algo.trading.exit_engine.TradeExecutor'):
        engine = ExitEngine(mock_config)

        mock_cur = MagicMock()

        with patch.object(engine, '_fetch_alpaca_quote', return_value=None):
            # Both queries return empty
            mock_cur.fetchall.side_effect = [
                [],  # No data today
                [],  # No data ever
            ]

            with pytest.raises(RuntimeError) as exc_info:
                engine._fetch_recent_prices(mock_cur, 'DELISTED', date(2026, 7, 21))

            assert "No price history available" in str(exc_info.value)


def test_fetch_recent_prices_single_price_point_raises(mock_config):
    """Test that we need at least 2 prices (current and previous close)."""
    with patch('algo.trading.exit_engine.TradeExecutor'):
        engine = ExitEngine(mock_config)

        mock_cur = MagicMock()

        with patch.object(engine, '_fetch_alpaca_quote', return_value=None):
            # Only one price point
            mock_cur.fetchall.side_effect = [
                [],  # No prices today
                [
                    (date(2026, 7, 19), Decimal('98.50')),  # only one price
                ]
            ]

            with pytest.raises(RuntimeError) as exc_info:
                engine._fetch_recent_prices(mock_cur, 'NEWSTOCK', date(2026, 7, 21))

            assert "Insufficient price history" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
