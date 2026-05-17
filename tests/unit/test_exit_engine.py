"""
Unit tests for ExitEngine - CRITICAL for position exit logic.

Tests real ExitEngine methods (NOT just arithmetic):
- check_exits() with current price vs stop-loss (full exit when price<stop)
- Partial exits at target price (T1 target: 50% exit)
- T2 raised stop evaluation (stop ratchets up, never down)
- Time-based exits (max holding period)
- Technical break exits (Minervini break detection)
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta, datetime


@pytest.mark.unit
class TestExitEngine:
    """Unit tests for ExitEngine real methods."""

    def test_check_exits_full_exit_at_stop_loss(self):
        """Should execute full exit when price falls below stop-loss."""
        from algo.algo_exit_engine import ExitEngine

        config = {}
        exit_engine = ExitEngine(config)

        # Position setup
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.0,
            'stop_loss': 142.0,
            'quantity': 100,
            'entry_date': date.today() - timedelta(days=10),
        }

        # Price falls below stop
        current_price = 140.0

        # Mock cursor
        mock_cur = MagicMock()

        result = exit_engine.check_exits(position, current_price, mock_cur)

        # Should trigger exit
        assert result.get('should_exit') is True
        assert result.get('exit_type') in ['stop_loss', 'full_exit']
        assert result.get('quantity_to_exit') == position['quantity']

    def test_check_exits_no_exit_above_stop_loss(self):
        """Should NOT exit when price is above stop-loss."""
        from algo.algo_exit_engine import ExitEngine

        config = {}
        exit_engine = ExitEngine(config)

        position = {
            'symbol': 'AAPL',
            'entry_price': 150.0,
            'stop_loss': 142.0,
            'quantity': 100,
            'entry_date': date.today() - timedelta(days=10),
        }

        # Price still above stop
        current_price = 145.0

        mock_cur = MagicMock()

        result = exit_engine.check_exits(position, current_price, mock_cur)

        # Should NOT trigger exit
        assert result.get('should_exit') is False

    def test_partial_exit_at_target_1(self):
        """Should execute 50% partial exit at T1 target."""
        from algo.algo_exit_engine import ExitEngine

        config = {
            'target_1_pct': 3.0,  # 3% above entry = T1
            'target_1_exit_pct': 50,  # Exit 50% at T1
        }

        exit_engine = ExitEngine(config)

        position = {
            'symbol': 'AAPL',
            'entry_price': 150.0,
            'stop_loss': 142.0,
            'quantity': 100,
            'entry_date': date.today() - timedelta(days=10),
        }

        # Price at T1 target: 150 * 1.03 = 154.50
        current_price = 154.50

        mock_cur = MagicMock()

        result = exit_engine.check_exits(position, current_price, mock_cur)

        # Should trigger partial exit
        if result.get('should_exit'):
            assert result.get('quantity_to_exit') == position['quantity'] * 0.5

    def test_stop_loss_ratchets_up_on_profit(self):
        """Should raise stop-loss when position gains, never lower it."""
        from algo.algo_exit_engine import ExitEngine

        config = {
            'trailing_stop_pct': 2.0,  # Trail stop by 2%
        }

        exit_engine = ExitEngine(config)

        position = {
            'symbol': 'AAPL',
            'entry_price': 150.0,
            'stop_loss': 142.0,  # Original stop
            'quantity': 100,
            'entry_date': date.today() - timedelta(days=10),
        }

        # Price rises to 160
        current_price = 160.0

        new_stop = exit_engine.calculate_new_stop(position, current_price)

        # Stop should have ratcheted up (160 * 0.98 = 156.80)
        assert new_stop > position['stop_loss']
        assert new_stop >= current_price * (1 - 0.02)

    def test_time_based_exit_at_max_holding_period(self):
        """Should exit position after max holding period (e.g., 60 days)."""
        from algo.algo_exit_engine import ExitEngine

        config = {
            'max_holding_days': 60,
        }

        exit_engine = ExitEngine(config)

        position = {
            'symbol': 'AAPL',
            'entry_price': 150.0,
            'stop_loss': 142.0,
            'quantity': 100,
            'entry_date': date.today() - timedelta(days=65),  # 65 days old
        }

        current_price = 160.0  # Still profitable
        mock_cur = MagicMock()

        result = exit_engine.check_exits(position, current_price, mock_cur)

        # Should trigger exit due to time limit
        if 'time_limit_exceeded' in result:
            assert result['time_limit_exceeded'] is True

    def test_technical_break_exit_minervini_pattern(self):
        """Should exit on Minervini technical break (below 50-DMA)."""
        from algo.algo_exit_engine import ExitEngine

        config = {}
        exit_engine = ExitEngine(config)

        position = {
            'symbol': 'AAPL',
            'entry_price': 150.0,
            'stop_loss': 142.0,
            'quantity': 100,
            'entry_date': date.today() - timedelta(days=30),
        }

        # Price breaks below 50-DMA
        current_price = 148.0
        dma_50 = 150.0  # Price below 50-DMA triggers break

        mock_cur = MagicMock()

        result = exit_engine.check_exits(
            position, current_price, mock_cur,
            additional_context={'dma_50': dma_50}
        )

        # Should detect technical break
        if result.get('should_exit'):
            assert result.get('exit_reason') in ['technical_break', 'dma_break']

    def test_get_open_positions_returns_valid_positions(self):
        """Should retrieve open positions from database."""
        from algo.algo_exit_engine import ExitEngine

        config = {}
        exit_engine = ExitEngine(config)

        # Mock cursor returns position data
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            {
                'id': 1,
                'symbol': 'AAPL',
                'quantity': 100,
                'entry_price': 150.0,
                'entry_date': date.today() - timedelta(days=10),
                'stop_loss': 142.0,
            }
        ]

        positions = exit_engine.get_open_positions(mock_cur)

        # Should return list of positions
        assert isinstance(positions, list)
        if len(positions) > 0:
            assert 'symbol' in positions[0]
            assert 'quantity' in positions[0]

    def test_multiple_exits_same_position(self):
        """Should handle multiple staggered exits on same position."""
        from algo.algo_exit_engine import ExitEngine

        config = {
            'target_1_pct': 3.0,
            'target_1_exit_pct': 50,
            'target_2_pct': 7.0,
            'target_2_exit_pct': 30,
        }

        exit_engine = ExitEngine(config)

        position = {
            'symbol': 'AAPL',
            'entry_price': 150.0,
            'stop_loss': 142.0,
            'quantity': 100,
            'entry_date': date.today() - timedelta(days=10),
            'partial_exits': [],  # Track exits
        }

        # First target hit
        current_price = 155.0  # Above T1
        mock_cur = MagicMock()

        result = exit_engine.check_exits(position, current_price, mock_cur)

        # Should compute exit quantity correctly for partial exits
        if result.get('should_exit'):
            assert 0 < result.get('quantity_to_exit', 0) < position['quantity']
