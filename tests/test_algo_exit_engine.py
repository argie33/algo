"""
Unit tests for algo_exit_engine - multi-tier exit targeting.

Tests cover:
- Tier 1 targets (conservative, 3-5% profit)
- Tier 2 targets (medium, 5-8% profit)
- Tier 3 targets (aggressive, 8-12% profit)
- Partial exit rules (sell 1/3 at T1, 1/3 at T2, hold 1/3 to T3+)
- Trailing stops (ratchet up, never down)
- Minervini breakout exits (fail back through 50-day MA)
- Time-based exits (max hold 60 days)
- Earnings event exits (close before earnings)

Critical for production: Bad exit targeting = profits become losses.
Missing stops = catastrophic losses on gap downs.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timedelta
from algo.algo_exit_engine import ExitEngine


class TestExitTargeting:
    """Test exit target calculations."""

    @pytest.fixture
    def exit_engine(self):
        """Create exit engine for testing."""
        engine = ExitEngine(
            db_host=os.environ.get('DB_HOST', 'localhost'),
            db_name='stocks',
            user='stocks',
            password=os.environ.get('DB_PASSWORD', 'test')
        )
        engine.cur = MagicMock()
        engine.conn = MagicMock()
        return engine

    # ========================================================================
    # Tier-based Targets
    # ========================================================================

    def test_calculate_tier_1_target(self, exit_engine):
        """Should calculate Tier 1 (conservative) target: +3% to +5%."""
        entry = 150.00
        target = exit_engine.calculate_tier_1_target(entry)

        target_pct = (target - entry) / entry * 100
        assert 3.0 <= target_pct <= 5.0

    def test_calculate_tier_2_target(self, exit_engine):
        """Should calculate Tier 2 (medium) target: +5% to +8%."""
        entry = 150.00
        target = exit_engine.calculate_tier_2_target(entry)

        target_pct = (target - entry) / entry * 100
        assert 5.0 <= target_pct <= 8.0

    def test_calculate_tier_3_target(self, exit_engine):
        """Should calculate Tier 3 (aggressive) target: +8% to +12%."""
        entry = 150.00
        target = exit_engine.calculate_tier_3_target(entry)

        target_pct = (target - entry) / entry * 100
        assert 8.0 <= target_pct <= 12.0

    def test_tier_targets_increase_sequentially(self, exit_engine):
        """Tier targets should increase: T1 < T2 < T3."""
        entry = 150.00
        t1 = exit_engine.calculate_tier_1_target(entry)
        t2 = exit_engine.calculate_tier_2_target(entry)
        t3 = exit_engine.calculate_tier_3_target(entry)

        assert t1 < t2 < t3

    # ========================================================================
    # Partial Exit Rules
    # ========================================================================

    def test_partial_exit_at_tier_1(self, exit_engine):
        """Should execute 1/3 exit at Tier 1 target."""
        position = {
            'symbol': 'AAPL',
            'quantity': 300,
            'entry_price': 150.00,
        }

        exit_signals = exit_engine.generate_partial_exits(
            position,
            current_price=154.50,  # At T1 target (+3%)
            entry_date=date.today()
        )

        # Should generate partial exit signal
        tier_1_exits = [e for e in exit_signals if e.tier == ExitTier.TIER_1]
        assert len(tier_1_exits) > 0
        assert tier_1_exits[0].quantity == 100  # 1/3 of 300

    def test_partial_exit_at_tier_2(self, exit_engine):
        """Should execute 1/3 exit at Tier 2 target."""
        position = {
            'symbol': 'AAPL',
            'quantity': 300,
            'entry_price': 150.00,
        }

        exit_signals = exit_engine.generate_partial_exits(
            position,
            current_price=157.50,  # At T2 target (+5%)
            entry_date=date.today()
        )

        tier_2_exits = [e for e in exit_signals if e.tier == ExitTier.TIER_2]
        assert len(tier_2_exits) > 0
        assert tier_2_exits[0].quantity == 100  # 1/3 of 300

    def test_hold_remaining_at_tier_3(self, exit_engine):
        """Should hold 1/3 at Tier 3 target."""
        position = {
            'symbol': 'AAPL',
            'quantity': 300,
            'entry_price': 150.00,
        }

        exit_signals = exit_engine.generate_partial_exits(
            position,
            current_price=162.00,  # At T3 target (+8%)
            entry_date=date.today()
        )

        tier_3_exits = [e for e in exit_signals if e.tier == ExitTier.TIER_3]
        # At T3, should have 1/3 remaining (not yet exited)
        assert any(e.quantity == 100 for e in tier_3_exits)

    # ========================================================================
    # Stop Loss Calculations
    # ========================================================================

    def test_calculate_initial_stop_loss(self, exit_engine):
        """Should set initial stop loss below entry."""
        entry = 150.00
        stop_pct = 2.0  # 2% stop

        stop = exit_engine.calculate_stop_loss(entry, stop_pct)

        assert stop == 147.00
        assert stop < entry

    def test_trailing_stop_increases_on_new_high(self, exit_engine):
        """Should ratchet up trailing stop on new highs."""
        entry = 150.00
        initial_stop = 147.00

        # Price reaches 160
        new_stop = exit_engine.update_trailing_stop(
            current_stop=initial_stop,
            current_price=160.00,
            entry_price=entry,
            stop_pct=2.0
        )

        # Stop should move up
        assert new_stop > initial_stop
        assert new_stop > 158.00  # 2% below 160

    def test_trailing_stop_never_moves_down(self, exit_engine):
        """Should never lower the trailing stop on pullback."""
        current_stop = 158.00  # Stop at 2% below 160

        # Price pulls back to 155
        new_stop = exit_engine.update_trailing_stop(
            current_stop=current_stop,
            current_price=155.00,
            entry_price=150.00,
            stop_pct=2.0
        )

        # Stop should stay at same level (not move down)
        assert new_stop == current_stop

    # ========================================================================
    # Minervini Breakout Exit
    # ========================================================================

    def test_minervini_exit_on_close_below_50ma(self, exit_engine):
        """Should trigger exit if price closes below 50-day MA (Minervini rule)."""
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.00,
            'entry_date': date.today() - timedelta(days=20),
        }

        current_price = 158.00
        ma_50 = 157.50

        # Price is above 50-day MA
        signal = exit_engine.check_minervini_exit(
            position,
            current_price=current_price,
            ma_50=ma_50
        )

        # Should not exit yet
        assert signal is None

        # Now price closes below 50-day MA
        signal = exit_engine.check_minervini_exit(
            position,
            current_price=156.00,  # Below 157.50
            ma_50=ma_50
        )

        # Should trigger exit
        assert signal is not None
        assert 'minervini' in signal.reason.lower()

    def test_minervini_exit_considers_profit(self, exit_engine):
        """Should not trigger Minervini exit if barely in profit (<3%)."""
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.00,
            'entry_date': date.today() - timedelta(days=20),
        }

        current_price = 151.50  # Only +1%, barely profitable
        ma_50 = 151.00

        signal = exit_engine.check_minervini_exit(
            position,
            current_price=150.99,  # Closes below MA
            ma_50=ma_50,
            min_profit_pct=3.0
        )

        # Should not exit if barely profitable
        assert signal is None

    # ========================================================================
    # Time-Based Exits
    # ========================================================================

    def test_time_based_exit_after_60_days(self, exit_engine):
        """Should force exit after 60 days maximum hold."""
        entry_date = date.today() - timedelta(days=60)
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.00,
            'entry_date': entry_date,
        }

        signal = exit_engine.check_time_based_exit(
            position,
            max_hold_days=60
        )

        assert signal is not None
        assert 'time' in signal.reason.lower() or '60' in signal.reason

    def test_no_time_based_exit_before_max_hold(self, exit_engine):
        """Should not exit before max hold period."""
        entry_date = date.today() - timedelta(days=30)
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.00,
            'entry_date': entry_date,
        }

        signal = exit_engine.check_time_based_exit(
            position,
            max_hold_days=60
        )

        assert signal is None

    # ========================================================================
    # Earnings Event Exits
    # ========================================================================

    def test_exit_before_earnings_announcement(self, exit_engine):
        """Should close position the day before earnings."""
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.00,
            'current_price': 155.00,
            'entry_date': date.today() - timedelta(days=20),
        }

        earnings_date = date.today() + timedelta(days=1)

        signal = exit_engine.check_earnings_exit(
            position,
            earnings_date=earnings_date,
            exit_before_days=1
        )

        assert signal is not None
        assert 'earnings' in signal.reason.lower()

    def test_no_exit_if_earnings_far_away(self, exit_engine):
        """Should not exit if earnings are >2 weeks away."""
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.00,
            'entry_date': date.today() - timedelta(days=20),
        }

        earnings_date = date.today() + timedelta(days=30)

        signal = exit_engine.check_earnings_exit(
            position,
            earnings_date=earnings_date,
            exit_before_days=1
        )

        # Should not exit
        assert signal is None


class TestExitEdgeCases:
    """Test edge cases in exit logic."""

    @pytest.fixture
    def exit_engine(self):
        """Create exit engine for testing."""
        engine = ExitEngine(
            db_host=os.environ.get('DB_HOST', 'localhost'),
            db_name='stocks',
            user='stocks',
            password=os.environ.get('DB_PASSWORD', 'test')
        )
        engine.cur = MagicMock()
        engine.conn = MagicMock()
        return engine

    def test_handle_gap_down_below_stop(self, exit_engine):
        """Should handle gap down that jumps below stop loss."""
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.00,
            'current_price': 145.00,
            'stop_loss': 147.00,
        }

        # Gap down to 143 (below stop)
        signal = exit_engine.check_stop_loss(
            position,
            current_price=143.00
        )

        assert signal is not None
        assert 'stop' in signal.reason.lower()

    def test_handle_zero_position_size(self, exit_engine):
        """Should handle positions with zero or missing quantity."""
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.00,
            'quantity': 0,
        }

        signal = exit_engine.check_minervini_exit(
            position,
            current_price=160.00,
            ma_50=155.00
        )

        # Should handle gracefully (no exit for zero position)
        assert signal is None or 'quantity' in signal.reason.lower()

    def test_handle_very_small_position(self, exit_engine):
        """Should handle very small fractional positions."""
        position = {
            'symbol': 'AAPL',
            'entry_price': 150.00,
            'quantity': 0.5,
        }

        signals = exit_engine.generate_partial_exits(
            position,
            current_price=155.00,
            entry_date=date.today()
        )

        # Should still work with fractional shares
        assert isinstance(signals, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
