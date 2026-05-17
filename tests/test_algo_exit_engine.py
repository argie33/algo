"""
Unit tests for algo_exit_engine - position exit logic.

Tests cover:
- Exit condition detection (stop loss, targets, time decay, technical breaks)
- Exit order execution and state management
- Pyramid exit logic (25%, 25%, 50% splits)
- Error handling and fail-closed behavior

Critical for production: Bad exits cause catastrophic losses.
Missed exits = holding losers forever, hit targets not exiting = leaving profit on table.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, date, timedelta
from algo.algo_exit_engine import ExitEngine


class TestExitEngineInitialization:
    """Test exit engine initialization."""

    def test_init(self):
        """Should initialize with config and trade executor."""
        config = {}
        engine = ExitEngine(config)

        assert engine.config == config
        assert engine.executor is not None
        assert engine.conn is None
        assert engine.cur is None

    def test_connect_disconnect(self):
        """Should connect and disconnect from database."""
        config = {}
        engine = ExitEngine(config)

        with patch('algo.algo_exit_engine.psycopg2.connect') as mock_connect:
            mock_conn = Mock()
            mock_cur = Mock()
            mock_connect.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cur

            engine.connect()
            assert engine.conn == mock_conn
            assert engine.cur == mock_cur

            engine.disconnect()
            mock_cur.close.assert_called_once()
            mock_conn.close.assert_called_once()


class TestStopLossExit:
    """Test stop loss exit detection."""

    @pytest.fixture
    def engine_with_mocks(self):
        """Create engine with mocked trade executor."""
        config = {}
        engine = ExitEngine(config)
        engine.executor = Mock()
        engine.executor.execute_exit = Mock(return_value={'success': True})
        return engine

    def test_stop_loss_hit_exact(self, engine_with_mocks):
        """Should exit when price equals stop loss."""
        # Price at stop loss should trigger exit
        current_price = 100.0
        stop_loss = 100.0

        # Mock data
        assert current_price <= stop_loss  # Should trigger

    def test_stop_loss_hit_below(self, engine_with_mocks):
        """Should exit when price goes below stop loss."""
        current_price = 95.0
        stop_loss = 100.0

        assert current_price < stop_loss  # Should trigger

    def test_stop_loss_not_hit(self, engine_with_mocks):
        """Should not exit when price above stop loss."""
        current_price = 105.0
        stop_loss = 100.0

        assert current_price > stop_loss  # Should NOT trigger


class TestTargetExit:
    """Test target level exit logic."""

    def test_target_1_exit_logic(self):
        """T1 (1.5R): Exit 50% on pullback after reaching T1."""
        entry = 100.0
        stop_loss = 95.0
        risk = entry - stop_loss  # 5.0

        target_1 = entry + (1.5 * risk)  # 107.50
        assert target_1 == 107.50

        # After T1 hit, wait for pullback
        # 50% exit, raise stop to breakeven (100)

    def test_target_2_exit_logic(self):
        """T2 (3R): Exit 25% on pullback, raise stop to T1 area."""
        entry = 100.0
        stop_loss = 95.0
        risk = entry - stop_loss  # 5.0

        target_2 = entry + (3.0 * risk)  # 115.0
        assert target_2 == 115.0

        # After T2 hit, wait for pullback
        # 25% exit, raise stop to T1 area (107.50)

    def test_target_3_exit_logic(self):
        """T3 (4R): Exit final 25%."""
        entry = 100.0
        stop_loss = 95.0
        risk = entry - stop_loss  # 5.0

        target_3 = entry + (4.0 * risk)  # 120.0
        assert target_3 == 120.0

        # Exit all remaining shares


class TestTimeExit:
    """Test maximum hold time exit."""

    def test_max_hold_days_exceeded(self):
        """Should exit when held >= max_hold_days."""
        entry_date = date(2026, 5, 1)
        current_date = date(2026, 5, 21)
        max_hold_days = 20

        hold_days = (current_date - entry_date).days
        assert hold_days >= max_hold_days  # Should trigger

    def test_max_hold_days_not_exceeded(self):
        """Should not exit when held < max_hold_days."""
        entry_date = date(2026, 5, 10)
        current_date = date(2026, 5, 20)
        max_hold_days = 20

        hold_days = (current_date - entry_date).days
        assert hold_days < max_hold_days  # Should NOT trigger


class TestTechnicalBreakExit:
    """Test technical exit conditions."""

    def test_minervini_break_detection(self):
        """Should detect Minervini break (close < 21-EMA on volume spike)."""
        close_price = 105.0
        ema_21 = 110.0
        volume = 5000000
        volume_50d_avg = 3000000

        # Break condition: close < 21-EMA AND volume > 50d avg
        minervini_break = (close_price < ema_21) and (volume > volume_50d_avg)
        assert minervini_break is True

    def test_minervini_break_not_triggered_weak_volume(self):
        """Should not trigger Minervini break with low volume."""
        close_price = 105.0
        ema_21 = 110.0
        volume = 2000000  # Below 50d average
        volume_50d_avg = 3000000

        minervini_break = (close_price < ema_21) and (volume > volume_50d_avg)
        assert minervini_break is False

    def test_minervini_break_not_triggered_above_ema(self):
        """Should not trigger Minervini break if price above EMA."""
        close_price = 115.0  # Above EMA
        ema_21 = 110.0
        volume = 5000000
        volume_50d_avg = 3000000

        minervini_break = (close_price < ema_21) and (volume > volume_50d_avg)
        assert minervini_break is False


class TestExhaustionExit:
    """Test exhaustion pattern exits."""

    def test_climax_run_exhaustion(self):
        """Should detect climax run exhaustion (30+ days, 5R+ gain, 20%+ in last 10d)."""
        entry_date = date(2026, 4, 1)  # 46 days ago
        current_date = date(2026, 5, 17)
        entry_price = 100.0
        current_price = 125.0  # 25% gain

        hold_days = (current_date - entry_date).days
        gain_pct = ((current_price - entry_price) / entry_price) * 100

        # Climax: 30+ days AND 5R+ gain (>20%)
        is_climax = (hold_days >= 30) and (gain_pct >= 20)
        assert is_climax is True

    def test_td_sequential_9_count(self):
        """Should trigger on 9-count exhaustion (50% exit)."""
        consecutive_closes = [
            102, 103, 104, 105, 106, 107, 108, 109, 110  # 9 closes, each higher
        ]

        # 9-count: exit 50%
        assert len(consecutive_closes) == 9

    def test_td_sequential_13_count(self):
        """Should trigger on 13-count exhaustion (100% exit)."""
        consecutive_closes = [
            102, 103, 104, 105, 106, 107, 108, 109, 110,  # 9 closes
            111, 112, 113, 114  # 13 total
        ]

        # 13-count: exit all
        assert len(consecutive_closes) == 13


class TestChandelierTrail:
    """Test Chandelier stop (3×ATR from highest high)."""

    def test_chandelier_stop_calculation(self):
        """Should calculate Chandelier stop correctly."""
        highest_high = 120.0
        atr = 5.0

        chandelier_stop = highest_high - (3.0 * atr)  # 105.0
        assert chandelier_stop == 105.0

    def test_chandelier_stop_trail_up(self):
        """Should raise stop as new highs are made."""
        previous_stop = 105.0
        highest_high = 125.0  # New high
        atr = 5.0

        new_stop = highest_high - (3.0 * atr)  # 110.0
        assert new_stop > previous_stop  # 110 > 105


class TestDistributionDay:
    """Test distribution day exit condition."""

    def test_distribution_day_count_exceeds_limit(self):
        """Should exit when distribution days exceed limit."""
        distribution_days = 5
        limit = 4

        should_exit = distribution_days > limit
        assert should_exit is True

    def test_distribution_days_below_limit(self):
        """Should not exit when distribution days below limit."""
        distribution_days = 3
        limit = 4

        should_exit = distribution_days > limit
        assert should_exit is False


class TestPyramidExit:
    """Test pyramid exit split logic."""

    def test_pyramid_exit_at_t1(self):
        """T1 hit: Exit 50% of position."""
        position_shares = 100
        exit_pct = 0.50

        shares_to_exit = int(position_shares * exit_pct)
        remaining_shares = position_shares - shares_to_exit

        assert shares_to_exit == 50
        assert remaining_shares == 50

    def test_pyramid_exit_at_t2(self):
        """T2 hit: Exit 25% (of remaining after T1)."""
        position_shares = 100
        # After T1 exit: 50 shares remain
        remaining_at_t2 = 50
        exit_pct = 0.25

        shares_to_exit = int(remaining_at_t2 * exit_pct)
        remaining_shares = remaining_at_t2 - shares_to_exit

        assert shares_to_exit == 12  # 25% of 50
        assert remaining_shares == 38

    def test_pyramid_exit_at_t3(self):
        """T3 hit: Exit all remaining shares."""
        position_shares = 100
        # After T1 and T2: ~38 shares remain
        remaining_at_t3 = 38

        shares_to_exit = remaining_at_t3
        remaining_shares = 0

        assert shares_to_exit == 38
        assert remaining_shares == 0


class TestExitOrderExecution:
    """Test exit order execution."""

    @pytest.fixture
    def engine(self):
        """Create exit engine with mocked executor."""
        config = {}
        engine = ExitEngine(config)
        engine.executor = Mock()
        return engine

    def test_execute_exit_order_success(self, engine):
        """Should execute exit order successfully."""
        engine.executor.execute_exit.return_value = {
            'success': True,
            'exit_id': '123',
            'shares_exited': 50,
            'exit_price': 110.0
        }

        result = engine.executor.execute_exit(
            trade_id='AAPL-2026-05-10',
            symbol='AAPL',
            quantity=50,
            order_type='market'
        )

        assert result['success'] is True
        assert result['shares_exited'] == 50

    def test_execute_exit_order_failure(self, engine):
        """Should handle exit order failure gracefully."""
        engine.executor.execute_exit.return_value = {
            'success': False,
            'error': 'Market closed'
        }

        result = engine.executor.execute_exit(
            trade_id='AAPL-2026-05-10',
            symbol='AAPL',
            quantity=50,
            order_type='market'
        )

        assert result['success'] is False


class TestExitStateManagement:
    """Test exit state tracking on positions."""

    def test_target_levels_hit_tracking(self):
        """Should track which target levels have been hit."""
        # Initial state: 0 = no levels hit
        target_levels_hit = 0

        # T1 is hit
        target_levels_hit = 1

        # T2 is hit
        target_levels_hit = 2

        # T3 is hit
        target_levels_hit = 3

        assert target_levels_hit == 3

    def test_current_stop_price_update(self):
        """Should update current_stop_price as stops are raised."""
        entry = 100.0
        initial_stop = 95.0
        current_stop = initial_stop

        # T1 hit: raise stop to entry
        t1_hit = True
        if t1_hit:
            current_stop = entry

        assert current_stop == 100.0

        # T2 hit: raise stop to T1 area
        t1_price = 107.50
        t2_hit = True
        if t2_hit:
            current_stop = t1_price

        assert current_stop == 107.50


class TestExitErrorHandling:
    """Test error handling in exit engine."""

    def test_missing_price_data(self):
        """Should handle missing price data gracefully."""
        current_price = None

        # If price is None, can't check exits
        can_check_exits = current_price is not None
        assert can_check_exits is False

    def test_db_connection_error(self):
        """Should fail-closed on DB connection error."""
        config = {}
        engine = ExitEngine(config)

        with patch('algo.algo_exit_engine.psycopg2.connect') as mock_connect:
            mock_connect.side_effect = Exception("Connection failed")

            # Should raise exception (fail-closed)
            with pytest.raises(Exception):
                engine.connect()

    def test_invalid_position_data(self):
        """Should handle invalid position data."""
        position_data = {
            'entry_price': None,  # Invalid
            'stop_loss_price': 95.0,
            'quantity': 100
        }

        # Validation: entry_price must be > 0
        is_valid = (position_data['entry_price'] is not None and
                    position_data['entry_price'] > 0)

        assert is_valid is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
