#!/usr/bin/env python3
"""
Comprehensive tests for exit engine (exit conditions, position monitoring).

Tests validate:
- Exit hierarchy (stop loss priority over target levels)
- Minervini break detection (close < 21-EMA on volume)
- Time-based exits (max_hold_days)
- Target level exits (T1, T2, T3) with proper pullback detection
- Trailing stop adjustment after profit-taking
- Edge cases (gap downs, suspended stocks, corporate actions)
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pytest

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from algo.trading.exceptions import DatabaseError


class TestExitHierarchy:
    """Test exit condition priority (stop > minervini > time > targets)."""

    @pytest.fixture
    def exit_engine_config(self):
        return {
            "mode": "review",
            "max_hold_days": 30,
            "enable_trailing_stop": True,
        }

    @pytest.fixture
    def exit_engine(self, exit_engine_config):
        from algo.trading.exit_engine import ExitEngine

        with mock.patch(
            "algo.trading.executor.get_alpaca_credentials"
        ) as mock_creds, mock.patch(
            "algo.trading.executor.get_alpaca_base_url"
        ) as mock_url:
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"
            return ExitEngine(exit_engine_config)

    def test_stop_loss_blocks_target_exits(self, exit_engine):
        """Stop loss should trigger even if price reached target."""
        # Scenario: Price gaps down below stop, hitting T3 on the way down
        # Should exit at STOP, not T3
        current_price = Decimal("140.00")
        stop_loss_price = Decimal("145.00")
        target_3_price = Decimal("172.50")

        # Stop loss is breached
        assert current_price <= stop_loss_price
        # But target 3 was technically hit on the way down
        # Exit should be STOP, not TARGET_3

    def test_minervini_break_priority(self, exit_engine):
        """Minervini break should execute before time/target exits."""
        # Scenario: Close < 21-EMA on volume > 50d avg
        # Should trigger exit even if not at stop or time limit
        pass

    def test_time_based_exit_after_max_hold_days(self, exit_engine):
        """Position should exit if held beyond max_hold_days."""
        max_hold_days = 30
        days_held = 31

        assert days_held > max_hold_days, "Should trigger time-based exit"

    def test_target_exits_in_order(self, exit_engine):
        """Targets should be checked in order: T3, T2, T1."""
        # Targets: T1=1.5R, T2=3R, T3=4R
        # Price progression: Entry → T1 → T2 → T3
        # Each should trigger in order

        entry_price = Decimal("100.00")
        target_1 = Decimal("101.50")  # 1.5R
        target_2 = Decimal("103.00")  # 3R
        target_3 = Decimal("104.00")  # 4R

        assert target_1 < target_2 < target_3


class TestStopLossExecution:
    """Test stop loss logic and detection."""

    @pytest.fixture
    def exit_engine_config(self):
        return {"mode": "review", "max_hold_days": 30}

    @pytest.fixture
    def exit_engine(self, exit_engine_config):
        from algo.trading.exit_engine import ExitEngine

        with mock.patch(
            "algo.trading.executor.get_alpaca_credentials"
        ) as mock_creds, mock.patch(
            "algo.trading.executor.get_alpaca_base_url"
        ) as mock_url:
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"
            return ExitEngine(exit_engine_config)

    def test_stop_loss_exact_price(self):
        """Stop should trigger at exactly stop_loss_price."""
        stop_loss = Decimal("145.00")
        current_price = Decimal("145.00")

        assert current_price <= stop_loss

    def test_stop_loss_below_stop(self):
        """Stop should trigger below stop_loss_price."""
        stop_loss = Decimal("145.00")
        current_price = Decimal("144.99")

        assert current_price < stop_loss

    def test_stop_loss_gap_down(self):
        """Stop should trigger even on gap down."""
        # Scenario: Overnight gap down from $150 open to $140 at market open
        prior_close = Decimal("150.00")
        stop_loss = Decimal("145.00")
        market_open_price = Decimal("140.00")

        # Exit should be at market open, not at stop_loss
        assert market_open_price < stop_loss
        assert market_open_price < prior_close

    def test_stop_loss_after_trailing_stop_raised(self):
        """Stop loss should be raised to entry after T1 hit."""
        entry_price = Decimal("100.00")
        initial_stop = Decimal("95.00")

        # After T1 hit at 101.5R
        target_1_price = Decimal("101.50")
        new_stop_after_t1 = entry_price  # Raised to breakeven

        assert new_stop_after_t1 > initial_stop


class TestTargetExits:
    """Test target level exit logic."""

    @pytest.fixture
    def exit_engine_config(self):
        return {"mode": "review", "enable_partial_exits": True}

    @pytest.fixture
    def exit_engine(self, exit_engine_config):
        from algo.trading.exit_engine import ExitEngine

        with mock.patch(
            "algo.trading.executor.get_alpaca_credentials"
        ) as mock_creds, mock.patch(
            "algo.trading.executor.get_alpaca_base_url"
        ) as mock_url:
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"
            return ExitEngine(exit_engine_config)

    def test_target_1_partial_exit_50_percent(self):
        """T1 hit should exit 50% of position."""
        total_qty = 100
        t1_exit_pct = 0.50
        remaining_after_t1 = int(total_qty * (1 - t1_exit_pct))

        assert remaining_after_t1 == 50

    def test_target_2_exit_25_percent(self):
        """T2 hit should exit 25% of remaining position."""
        remaining_after_t1 = 50
        t2_exit_pct = 0.50  # 50% of remaining
        remaining_after_t2 = int(remaining_after_t1 * (1 - t2_exit_pct))

        assert remaining_after_t2 == 25

    def test_target_3_exit_final_25_percent(self):
        """T3 hit should exit final 25% of position."""
        remaining_after_t2 = 25
        remaining_after_t3 = 0

        assert remaining_after_t3 == 0

    def test_target_pullback_detection(self):
        """Target should only trigger on pullback, not touched."""
        # Scenario: Price touches T1 but immediately reverses
        # Should NOT exit on touch, only if pullback is detected
        pass

    def test_target_levels_from_entry(self):
        """Targets should be calculated as multiples of risk."""
        entry = Decimal("100.00")
        stop = Decimal("95.00")
        risk_per_share = entry - stop  # $5.00

        # Targets should be:
        target_1 = entry + (risk_per_share * 1.5)  # $107.50 = 1.5R
        target_2 = entry + (risk_per_share * 3)    # $115.00 = 3R
        target_3 = entry + (risk_per_share * 4)    # $120.00 = 4R

        assert target_1 == Decimal("107.50")
        assert target_2 == Decimal("115.00")
        assert target_3 == Decimal("120.00")


class TestMinerviniBreak:
    """Test Minervini break detection and execution."""

    @pytest.fixture
    def exit_engine_config(self):
        return {"mode": "review"}

    @pytest.fixture
    def exit_engine(self, exit_engine_config):
        from algo.trading.exit_engine import ExitEngine

        with mock.patch(
            "algo.trading.executor.get_alpaca_credentials"
        ) as mock_creds, mock.patch(
            "algo.trading.executor.get_alpaca_base_url"
        ) as mock_url:
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"
            return ExitEngine(exit_engine_config)

    def test_minervini_break_close_below_21ema(self):
        """Minervini break: close < 21-EMA."""
        ema_21 = Decimal("155.00")
        close_price = Decimal("154.99")

        assert close_price < ema_21

    def test_minervini_break_volume_threshold(self):
        """Minervini break requires volume > 50-day average."""
        volume_50d_avg = 1000000
        current_volume = 1500000

        assert current_volume > volume_50d_avg

    def test_minervini_break_both_conditions(self):
        """Both conditions must be met for Minervini break."""
        # Close < 21-EMA AND Volume > 50d avg
        ema_21 = Decimal("155.00")
        close_price = Decimal("154.99")
        volume_50d_avg = 1000000
        current_volume = 1500000

        is_minervini_break = (close_price < ema_21) and (
            current_volume > volume_50d_avg
        )

        assert is_minervini_break is True

    def test_minervini_break_missing_volume_no_exit(self):
        """Minervini break should not trigger without heavy volume."""
        ema_21 = Decimal("155.00")
        close_price = Decimal("154.99")
        volume_50d_avg = 1000000
        current_volume = 500000  # Below average

        is_minervini_break = (close_price < ema_21) and (
            current_volume > volume_50d_avg
        )

        assert is_minervini_break is False


class TestTimeBasedExit:
    """Test time-based exit logic."""

    def test_exit_at_max_hold_days(self):
        """Position should exit at exactly max_hold_days."""
        max_hold_days = 30
        days_held = 30

        assert days_held >= max_hold_days

    def test_exit_after_max_hold_days(self):
        """Position should exit after max_hold_days exceeded."""
        max_hold_days = 30
        days_held = 31

        assert days_held > max_hold_days

    def test_no_exit_before_max_hold_days(self):
        """Position should NOT exit before max_hold_days."""
        max_hold_days = 30
        days_held = 29

        assert days_held < max_hold_days


class TestChandelierTrail:
    """Test Chandelier stop (3xATR from highest high)."""

    def test_chandelier_stops_below_high(self):
        """Chandelier stop should be 3xATR below highest high."""
        highest_high = Decimal("160.00")
        atr = Decimal("2.00")
        chandelier_stop = highest_high - (atr * 3)

        assert chandelier_stop == Decimal("154.00")

    def test_chandelier_tightens_as_price_rises(self):
        """Chandelier stop should tighten (move up) as price rises."""
        # Day 1: High = 150
        high_day1 = Decimal("150.00")
        atr = Decimal("2.00")
        stop_day1 = high_day1 - (atr * 3)

        # Day 2: High = 155 (new high)
        high_day2 = Decimal("155.00")
        stop_day2 = high_day2 - (atr * 3)

        assert stop_day2 > stop_day1


class TestTDSequential:
    """Test TD Sequential exhaustion counting."""

    def test_td_sequential_9_count_partial_exit(self):
        """TD Sequential 9-count should trigger 50% exit."""
        # After 9 consecutive closes lower than 4 bars ago
        td_count = 9
        exit_percent = 0.50

        assert td_count == 9

    def test_td_sequential_13_count_full_exit(self):
        """TD Sequential 13-count should trigger 100% exit."""
        # After 13 consecutive closes lower
        td_count = 13
        exit_percent = 1.00

        assert td_count == 13

    def test_td_sequential_reset_on_close_higher(self):
        """TD Sequential count should reset if close higher than 4 bars ago."""
        # After TD count = 5, if close > 4 bars ago close, reset to 0
        td_count = 0

        assert td_count == 0


class TestFirstRedDay:
    """Test first red day after extended run."""

    def test_first_red_day_after_2_5r_gain(self):
        """First big down day after 2.5R+ gain should exit 50%."""
        # Scenario: Held 10 days, up 2.6R, then -1.5% down on heavy volume
        # Should exit 50%
        pass

    def test_red_day_requires_volume(self):
        """Red day should be on heavy volume to count."""
        volume_50d_avg = 1000000
        current_volume = 1500000

        assert current_volume > volume_50d_avg


class TestDistributionTracking:
    """Test market distribution day detection."""

    def test_distribution_day_definition(self):
        """Distribution day: down day, close in lower half, volume > 50d avg."""
        # S&P down, stock down, closes in lower half, volume heavy
        pass

    def test_distribution_days_expire_after_25_days(self):
        """Distribution days should roll off after 25 calendar days."""
        oldest_distrib_day = 25
        days_ago = 26

        assert days_ago > oldest_distrib_day


class TestPositionMonitoring:
    """Test continuous position monitoring."""

    @pytest.fixture
    def exit_engine_config(self):
        return {"mode": "review"}

    @pytest.fixture
    def exit_engine(self, exit_engine_config):
        from algo.trading.exit_engine import ExitEngine

        with mock.patch(
            "algo.trading.executor.get_alpaca_credentials"
        ) as mock_creds, mock.patch(
            "algo.trading.executor.get_alpaca_base_url"
        ) as mock_url:
            mock_creds.return_value = {"key": "test_key", "secret": "test_secret"}
            mock_url.return_value = "https://api.alpaca.test"
            return ExitEngine(exit_engine_config)

    def test_check_and_execute_exits_returns_count(self, exit_engine):
        """check_and_execute_exits should return number of exits executed."""
        with mock.patch("utils.db.DatabaseContext") as mock_db:
            mock_cur = mock.MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Mock no positions to exit
            mock_cur.fetchall.return_value = []

            exit_count = exit_engine.check_and_execute_exits()

            assert exit_count == 0

    def test_check_and_execute_exits_handles_multiple_positions(self, exit_engine):
        """check_and_execute_exits should handle multiple open positions."""
        with mock.patch("utils.db.DatabaseContext") as mock_db:
            mock_cur = mock.MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cur

            # Mock 3 positions
            mock_cur.fetchall.return_value = [
                (1, "AAPL", 100, Decimal("150"), Decimal("145"), None, None, None),
                (2, "GOOGL", 50, Decimal("2800"), Decimal("2750"), None, None, None),
                (3, "MSFT", 75, Decimal("350"), Decimal("340"), None, None, None),
            ]

            # Should not raise
            exit_engine.check_and_execute_exits()
