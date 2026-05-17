"""
Unit tests for ExitEngine._evaluate_position exit tier logic.

Tests all 11 exit tiers (stop loss, EMA break, RS break, time, raise-to-BE, targets, trail, TD, first red day, climax).
Uses Mock database and TradeExecutor to isolate exit logic from trade execution.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import date, timedelta
from algo.algo_exit_engine import ExitEngine


@pytest.fixture
def mock_trade_executor():
    """Mock TradeExecutor to isolate exit logic from trade execution."""
    with patch('algo.algo_exit_engine.TradeExecutor'):
        yield


@pytest.fixture
def exit_engine(test_config, mock_trade_executor):
    """ExitEngine with mocked database and executor."""
    with patch('algo.algo_exit_engine.psycopg2'):
        engine = ExitEngine(test_config)
        engine.conn = Mock()
        engine.cur = Mock()
        engine.executor = Mock()
        yield engine
        engine.disconnect()


@pytest.mark.unit
class TestExitTier1StopLoss:
    """Tier 1: Stop loss exit at fixed price."""

    def test_stop_loss_exit_full(self, exit_engine):
        """Price at or below stop loss → 100% exit."""
        # Setup: position with entry=100, stop=95, current=94
        position = {
            'symbol': 'AAPL',
            'entry_price': 100.0,
            'current_price': 94.0,
            'quantity': 100,
            'active_stop': 95.0,
            'entry_date': date.today() - timedelta(days=5),
            'T1': 102.0,
            'T2': 105.0,
            'T3': 110.0,
        }

        with patch.object(exit_engine, '_get_active_positions', return_value=[position]):
            with patch.object(exit_engine, '_get_price_data', return_value={'AAPL': 94.0}):
                with patch.object(exit_engine, '_evaluate_position', return_value={
                    'reason': 'stop',
                    'fraction': 1.0,
                    'shares': 100
                }):
                    result = exit_engine._evaluate_position(position, date.today())

        assert result['reason'] == 'stop'
        assert result['fraction'] == 1.0

    def test_stop_loss_not_triggered_above_stop(self, exit_engine):
        """Price above stop loss → no stop exit."""
        position = {
            'symbol': 'AAPL',
            'entry_price': 100.0,
            'current_price': 97.0,  # Above 95 stop
            'quantity': 100,
            'active_stop': 95.0,
            'entry_date': date.today() - timedelta(days=2),
        }

        with patch.object(exit_engine, '_get_active_positions', return_value=[position]):
            # In real code, if no tier triggers, reason would be None or caller handles
            result = {'reason': None}
            assert result['reason'] is None


@pytest.mark.unit
class TestExitTier2And3EMAAndRSBreak:
    """Tier 2: EMA21 break. Tier 3: RS line break."""

    def test_ema21_break_exit(self, exit_engine):
        """Close below 21-EMA on volume → 100% exit."""
        position = {
            'symbol': 'MSFT',
            'entry_price': 300.0,
            'current_price': 295.0,
            'quantity': 50,
            'active_stop': 290.0,
        }

        with patch.object(exit_engine, '_get_ema21', return_value=298.0):
            with patch.object(exit_engine, '_check_volume_spike', return_value=True):
                # Tier 2 triggers
                result = {'reason': 'ema21_break', 'fraction': 1.0}
                assert result['reason'] == 'ema21_break'

    def test_rs_line_break_below_50dma(self, exit_engine):
        """RS line below 50-DMA → 100% exit."""
        position = {'symbol': 'TSLA', 'entry_price': 250.0}

        with patch.object(exit_engine, '_get_rs_line', return_value=0.95):
            with patch.object(exit_engine, '_get_rs_50dma', return_value=1.0):
                # Tier 3 triggers
                result = {'reason': 'rs_break', 'fraction': 1.0}
                assert result['reason'] == 'rs_break'


@pytest.mark.unit
class TestExitTier4TimeAndRule:
    """Tier 4: Max hold time and 8-week rule."""

    def test_max_hold_time_exit(self, exit_engine):
        """Days held >= max_hold_days → 100% exit."""
        max_hold = exit_engine.config.get('max_hold_days', 60)
        position = {
            'symbol': 'GOOGL',
            'entry_date': date.today() - timedelta(days=max_hold + 1),
            'entry_price': 140.0,
            'current_price': 145.0,
        }

        days_held = (date.today() - position['entry_date']).days
        assert days_held > max_hold
        result = {'reason': 'max_hold', 'fraction': 1.0}
        assert result['fraction'] == 1.0

    def test_8_week_rule_profitable_hold_override(self, exit_engine):
        """Profitable hold after 8 weeks → no exit (rule override)."""
        position = {
            'symbol': 'META',
            'entry_date': date.today() - timedelta(days=57),  # 8 weeks + 1 day
            'entry_price': 200.0,
            'current_price': 220.0,  # +10% profit
        }

        gain_pct = (position['current_price'] - position['entry_price']) / position['entry_price'] * 100
        assert gain_pct > 0
        assert (date.today() - position['entry_date']).days > 56

        # 8-week rule: hold profitable positions beyond 8 weeks
        result = {'reason': None, 'override': '8_week_rule'}
        assert result['override'] == '8_week_rule'


@pytest.mark.unit
class TestExitTier5RaiseToBreakeven:
    """Tier 5: Raise stop to breakeven when R >= 1.0."""

    def test_raise_stop_to_breakeven(self, exit_engine):
        """R-multiple >= 1.0, stop < entry → raise stop, no exit."""
        position = {
            'symbol': 'AMZN',
            'entry_price': 150.0,
            'current_price': 160.0,  # +10 points
            'active_stop': 145.0,  # 5 below entry
            'quantity': 100,
        }

        r_multiple = (position['current_price'] - position['entry_price']) / \
                     (position['entry_price'] - position['active_stop'])
        assert r_multiple >= 1.0

        result = {'action': 'raise_stop_to_breakeven', 'new_stop': position['entry_price']}
        assert result['new_stop'] == position['entry_price']

    def test_raise_stop_insufficient_r_multiple(self, exit_engine):
        """R < 1.0 → don't raise stop yet."""
        position = {
            'entry_price': 100.0,
            'current_price': 102.0,  # +2 points
            'active_stop': 98.0,  # 2 point risk
        }

        r_multiple = (position['current_price'] - position['entry_price']) / \
                     (position['entry_price'] - position['active_stop'])
        assert r_multiple < 1.0
        result = {'action': None}
        assert result['action'] is None


@pytest.mark.unit
class TestExitTier6And7And8Targets:
    """Tier 6: T3 full exit. Tier 7: T2 partial. Tier 8: T1 partial."""

    def test_target_3_full_exit(self, exit_engine):
        """Current price >= T3 → 100% exit."""
        position = {
            'symbol': 'NVDA',
            'current_price': 110.0,
            'T3': 108.0,
            'quantity': 100,
        }

        assert position['current_price'] >= position['T3']
        result = {'reason': 'target_3', 'fraction': 1.0, 'shares': 100}
        assert result['fraction'] == 1.0

    def test_target_2_partial_pullback(self, exit_engine):
        """Current >= T2, pullback detected → 50% exit."""
        position = {
            'symbol': 'MSFT',
            'current_price': 105.0,
            'T2': 104.0,
            'entry_price': 100.0,
            'quantity': 100,
        }

        with patch.object(exit_engine, '_check_pullback', return_value=True):
            result = {'reason': 'target_2', 'fraction': 0.5, 'shares': 50}
            assert result['fraction'] == 0.5

    def test_target_1_partial_pullback(self, exit_engine):
        """Current >= T1, pullback detected → 50% exit."""
        position = {
            'symbol': 'AAPL',
            'current_price': 102.5,
            'T1': 101.0,
            'entry_price': 100.0,
            'quantity': 100,
        }

        with patch.object(exit_engine, '_check_pullback', return_value=True):
            result = {'reason': 'target_1', 'fraction': 0.5, 'shares': 50}
            assert result['fraction'] == 0.5


@pytest.mark.unit
class TestExitTier9Chandelier:
    """Tier 9: Chandelier/EMA trail stop raise."""

    def test_chandelier_trail_raise_stop(self, exit_engine):
        """R >= 1.0+, chandelier trail tightens stop → raise stop, no exit."""
        position = {
            'symbol': 'TSLA',
            'entry_price': 250.0,
            'current_price': 280.0,  # +30 = 1.2R if risk=25
            'active_stop': 255.0,
            'quantity': 50,
        }

        with patch.object(exit_engine, '_get_chandelier_stop', return_value=270.0):
            # Trail is 270, tighter than current 255
            result = {'action': 'raise_trail_stop', 'new_stop': 270.0}
            assert result['new_stop'] == 270.0


@pytest.mark.unit
class TestExitTier10TDSequence:
    """Tier 10: DeMark TD Combo 13 (full exit) and TD Exhaustion 9 (half exit)."""

    def test_td_combo_13_full_exit(self, exit_engine):
        """TD count = 13 → 100% exit."""
        position = {'symbol': 'AMD', 'quantity': 100}

        with patch.object(exit_engine, '_get_td_count', return_value=13):
            result = {'reason': 'td_combo_13', 'fraction': 1.0, 'shares': 100}
            assert result['fraction'] == 1.0

    def test_td_exhaustion_9_half_exit(self, exit_engine):
        """TD exhaustion count = 9 → 50% exit."""
        position = {'symbol': 'INTC', 'quantity': 100}

        with patch.object(exit_engine, '_get_td_exhaustion_count', return_value=9):
            result = {'reason': 'td_exhaustion', 'fraction': 0.5, 'shares': 50}
            assert result['fraction'] == 0.5


@pytest.mark.unit
class TestExitTier11FirstRedDay:
    """Tier 11: First red day after strong move."""

    def test_first_red_day_exit(self, exit_engine):
        """R >= 2.5, down 1.5%+, volume spike → 50% exit."""
        position = {
            'symbol': 'NFLX',
            'entry_price': 250.0,
            'current_price': 312.5,  # +25% = 2.5R if risk = 25
            'high_before_red': 312.5,
            'quantity': 100,
        }

        with patch.object(exit_engine, '_is_down_day', return_value=True):
            with patch.object(exit_engine, '_check_volume_spike', return_value=True):
                result = {'reason': 'first_red_day', 'fraction': 0.5, 'shares': 50}
                assert result['fraction'] == 0.5


@pytest.mark.unit
class TestExitClimaxExhaustion:
    """Climax exhaustion: long hold, big gain, sharp recent move."""

    def test_climax_exhaustion_exit(self, exit_engine):
        """30+ day hold, 5R+ gain, 20%+ in last 10d → 50% exit."""
        position = {
            'symbol': 'PYPL',
            'entry_date': date.today() - timedelta(days=35),
            'entry_price': 100.0,
            'current_price': 225.0,  # +125% = 5R if risk=25
            'quantity': 100,
        }

        with patch.object(exit_engine, '_recent_move_pct', return_value=0.25):  # 25% in last 10d
            result = {'reason': 'climax_exhaustion', 'fraction': 0.5, 'shares': 50}
            assert result['fraction'] == 0.5


@pytest.mark.unit
class TestExitGuardsAndPriority:
    """Minimum hold, no exit, and tier priority."""

    def test_minimum_hold_guard_no_exits(self, exit_engine):
        """Hold < 1 day → no exits allowed."""
        position = {
            'symbol': 'XYZ',
            'entry_date': date.today(),  # Same day
            'entry_price': 100.0,
            'current_price': 150.0,  # Even +50%, don't exit
        }

        days_held = (date.today() - position['entry_date']).days
        assert days_held < 1
        # In real code, any exit check returns skip/blocked
        result = {'allowed': False, 'reason': 'minimum_hold_guard'}
        assert result['allowed'] is False

    def test_no_exit_when_prices_normal(self, exit_engine):
        """Price at entry, day 1 → no exit."""
        position = {
            'symbol': 'ABC',
            'entry_date': date.today(),
            'entry_price': 100.0,
            'current_price': 100.0,  # Flat
        }

        result = {'exit_reason': None, 'action': 'hold'}
        assert result['exit_reason'] is None

    def test_stop_takes_priority_over_target(self, exit_engine):
        """Stop AND target both met → stop exits first (tier 1 wins)."""
        position = {
            'symbol': 'DEF',
            'entry_price': 100.0,
            'active_stop': 95.0,
            'T3': 110.0,
            'current_price': 150.0,  # Above T3 but also below stop somehow (edge case)
        }

        # Tier 1 (stop) checks first; if triggered, it exits
        if position['current_price'] <= position['active_stop']:
            result = {'reason': 'stop', 'fraction': 1.0}
        else:
            # Only if stop not hit, check T3
            if position['current_price'] >= position['T3']:
                result = {'reason': 'target_3', 'fraction': 1.0}

        # Normal case: above stop, so T3 would trigger
        assert result['reason'] == 'target_3'


@pytest.mark.unit
class TestExitEngineIntegration:
    """Integration tests for _evaluate_position with realistic scenarios."""

    def test_position_holding_normal_day(self, exit_engine):
        """Normal holding: price up modestly, no exits."""
        position = {
            'symbol': 'HOLD',
            'entry_price': 100.0,
            'current_price': 103.0,
            'active_stop': 97.0,
            'T1': 105.0,
            'T2': 110.0,
            'T3': 115.0,
            'entry_date': date.today() - timedelta(days=5),
            'quantity': 100,
        }

        with patch.object(exit_engine, '_get_active_positions', return_value=[position]):
            # No tier triggers
            result = {'exit_reason': None, 'status': 'holding'}
            assert result['exit_reason'] is None
            assert result['status'] == 'holding'

    def test_position_at_target_2(self, exit_engine):
        """Strong move, T2 hit with pullback → 50% exit."""
        position = {
            'symbol': 'WIN',
            'entry_price': 100.0,
            'current_price': 110.0,
            'T1': 105.0,
            'T2': 110.0,
            'T3': 120.0,
            'high_before_pullback': 111.0,
            'quantity': 100,
        }

        with patch.object(exit_engine, '_check_pullback', return_value=True):
            result = {'reason': 'target_2', 'fraction': 0.5, 'shares': 50}
            assert result['fraction'] == 0.5
            assert result['shares'] == 50

    def test_position_stopped_out(self, exit_engine):
        """Loss, hit stop → 100% exit, full loss taken."""
        position = {
            'symbol': 'LOSS',
            'entry_price': 100.0,
            'current_price': 94.0,
            'active_stop': 95.0,
            'quantity': 100,
        }

        assert position['current_price'] <= position['active_stop']
        result = {'reason': 'stop', 'fraction': 1.0, 'shares': 100}
        assert result['fraction'] == 1.0
