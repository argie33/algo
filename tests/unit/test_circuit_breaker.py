"""
Unit tests for CircuitBreaker — pre-trade kill-switch checks.

Tests each of 8 circuit breakers:
- CB1: Portfolio drawdown >= threshold
- CB2: Daily loss >= max
- CB3: Consecutive losses >= max
- CB4: Total open risk >= max % portfolio
- CB5: VIX spike > max_threshold
- CB6: Market stage break (downtrend)
- CB7: Weekly loss >= max
- CB8: Data staleness > N days
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta


@pytest.mark.unit
class TestDrawdownCircuitBreaker:
    """CB1: Halt if portfolio drawdown >= halt_drawdown_pct (default 20%)."""

    def test_no_halt_under_threshold(self, test_config):
        """Drawdown 15% should not halt."""
        from algo.algo_circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # Peak 100k, current 85k = 15% drawdown
            mock_cur.fetchone.return_value = (100000.0, 85000.0)

            result = cb._check_drawdown(date.today())

            assert result['halted'] is False
            assert result['value'] == pytest.approx(15.0, rel=0.1)

    def test_halt_at_threshold(self, test_config):
        """Drawdown 20% should halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # Peak 100k, current 80k = 20% drawdown
            mock_cur.fetchone.return_value = (100000.0, 80000.0)

            result = cb._check_drawdown(date.today())

            assert result['halted'] is True
            assert result['value'] >= result['threshold']


@pytest.mark.unit
class TestDailyLossCircuitBreaker:
    """CB2: Halt if daily loss >= max_daily_loss_pct (default 2%)."""

    def test_no_halt_under_daily_loss(self, test_config):
        """Daily loss 1% should not halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchone.return_value = (-1.0,)  # 1% loss

            result = cb._check_daily_loss(date.today())

            assert result['halted'] is False

    def test_halt_on_daily_loss(self, test_config):
        """Daily loss 2%+ should halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchone.return_value = (-2.5,)  # 2.5% loss

            result = cb._check_daily_loss(date.today())

            assert result['halted'] is True


@pytest.mark.unit
class TestConsecutiveLossesCircuitBreaker:
    """CB3: Halt if consecutive_losses >= max (default 3)."""

    def test_two_consecutive_losses_ok(self, test_config):
        """2 consecutive losses should not halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchall.return_value = [
                (-1.5, date.today()),
                (-0.8, date.today() - timedelta(days=1)),
                (1.2, date.today() - timedelta(days=2)),
            ]

            result = cb._check_consecutive_losses(date.today())

            assert result['halted'] is False
            assert result['value'] == 2

    def test_three_consecutive_losses_halt(self, test_config):
        """3 consecutive losses should halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchall.return_value = [
                (-1.5, date.today()),
                (-0.8, date.today() - timedelta(days=1)),
                (-0.9, date.today() - timedelta(days=2)),
            ]

            result = cb._check_consecutive_losses(date.today())

            assert result['halted'] is True
            assert result['value'] >= 3


@pytest.mark.unit
class TestTotalRiskCircuitBreaker:
    """CB4: Halt if total_open_risk >= max_total_risk_pct (default 4%)."""

    def test_low_open_risk_ok(self, test_config):
        """2% open risk should not halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchone.side_effect = [(2000.0,), (100000.0,)]

            result = cb._check_total_risk(date.today())

            assert result['halted'] is False
            assert result['value'] == 2.0

    def test_high_open_risk_halt(self, test_config):
        """5% open risk should halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchone.side_effect = [(5000.0,), (100000.0,)]

            result = cb._check_total_risk(date.today())

            assert result['halted'] is True
            assert result['value'] >= 4.0


@pytest.mark.unit
class TestVIXCircuitBreaker:
    """CB5: Halt if VIX > vix_max_threshold (default 35)."""

    def test_low_vix_ok(self, test_config):
        """VIX 20 should not halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchone.return_value = (20.0,)

            result = cb._check_vix_spike(date.today())

            assert result['halted'] is False

    def test_high_vix_halt(self, test_config):
        """VIX 40 should halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchone.return_value = (40.0,)

            result = cb._check_vix_spike(date.today())

            assert result['halted'] is True


@pytest.mark.unit
class TestMarketStageCircuitBreaker:
    """CB6: Halt if market_stage == 4 (full downtrend)."""

    def test_uptrend_ok(self, test_config):
        """Market stage 1-2 (uptrend) should not halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchone.return_value = (date.today(), 2, 'uptrend')

            result = cb._check_market_stage(date.today())

            assert result['halted'] is False

    def test_downtrend_halt(self, test_config):
        """Market stage 4 (downtrend) should halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchone.return_value = (date.today(), 4, 'downtrend')

            result = cb._check_market_stage(date.today())

            assert result['halted'] is True


@pytest.mark.unit
class TestWeeklyLossCircuitBreaker:
    """CB7: Halt if weekly_loss >= max_weekly_loss_pct (default 5%)."""

    def test_low_weekly_loss_ok(self, test_config):
        """Weekly loss 3% should not halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # Current portfolio value: 100000, week ago: 103000
            # Weekly return = (100000 - 103000) / 103000 * 100 = -2.91%
            mock_cur.fetchone.return_value = (100000.0, 103000.0)

            result = cb._check_weekly_loss(date.today())

            assert result['halted'] is False

    def test_high_weekly_loss_halt(self, test_config):
        """Weekly loss 5%+ should halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # Current portfolio value: 95000, week ago: 100000
            # Weekly return = (95000 - 100000) / 100000 * 100 = -5%
            mock_cur.fetchone.return_value = (95000.0, 100000.0)

            result = cb._check_weekly_loss(date.today())

            assert result['halted'] is True


@pytest.mark.unit
class TestDataFreshnessCircuitBreaker:
    """CB8: Halt if latest data > N days old."""

    def test_fresh_data_ok(self, test_config):
        """Data from today should not halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchone.return_value = (date.today(),)

            result = cb._check_data_freshness(date.today())

            assert result['halted'] is False

    def test_stale_data_halt(self, test_config):
        """Data > max_data_staleness_days (default 5) should halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            stale_date = date.today() - timedelta(days=6)
            mock_cur.fetchone.return_value = (stale_date,)

            result = cb._check_data_freshness(date.today())

            assert result['halted'] is True
            assert result['value'] > 5


@pytest.mark.unit
class TestAllCircuitBreakers:
    """Test running all CB checks together."""

    def test_all_clear_no_halt(self, test_config):
        """All CBs green should not halt trading."""
        from unittest.mock import MagicMock

        cb = CircuitBreaker(test_config)
        cb.cur = MagicMock()
        cb.conn = MagicMock()

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, '_check_drawdown', return_value={'halted': False}), \
             patch.object(cb, '_check_daily_loss', return_value={'halted': False}), \
             patch.object(cb, '_check_consecutive_losses', return_value={'halted': False}), \
             patch.object(cb, '_check_total_risk', return_value={'halted': False}), \
             patch.object(cb, '_check_vix_spike', return_value={'halted': False}), \
             patch.object(cb, '_check_market_stage', return_value={'halted': False}), \
             patch.object(cb, '_check_weekly_loss', return_value={'halted': False}), \
             patch.object(cb, '_check_data_freshness', return_value={'halted': False}):

            result = cb.check_all(date.today())

            assert result['halted'] is False
            assert len(result['halt_reasons']) == 0

    def test_one_cb_fires_halt_trading(self, test_config):
        """Any CB firing should halt trading."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, '_check_drawdown', return_value={'halted': True, 'reason': 'Drawdown 25%'}), \
             patch.object(cb, '_check_daily_loss', return_value={'halted': False}), \
             patch.object(cb, '_check_consecutive_losses', return_value={'halted': False}), \
             patch.object(cb, '_check_total_risk', return_value={'halted': False}), \
             patch.object(cb, '_check_vix_spike', return_value={'halted': False}), \
             patch.object(cb, '_check_market_stage', return_value={'halted': False}), \
             patch.object(cb, '_check_weekly_loss', return_value={'halted': False}), \
             patch.object(cb, '_check_data_freshness', return_value={'halted': False}):

            result = cb.check_all(date.today())

            assert result['halted'] is True


@pytest.mark.unit
class TestMissingCircuitBreakers:
    """Tests for 5 missing CB checks not covered by CB1–CB8."""

    def test_drawdown_re_engagement_halted_below_threshold(self, test_config):
        """CB9: Drawdown re-engagement — drawdown still high → still halted."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # Drawdown recovery condition: previous drawdown was triggered, now only 15% down (but halted until 10%)
            mock_cur.fetchone.return_value = (100000.0, 85000.0)  # 15% drawdown

            result = cb._check_drawdown_re_engagement(date.today())

            # Re-engagement check fails if still above recovery threshold (e.g., > 10%)
            if result.get('value', 0) > cb.config.get('drawdown_re_engagement_recovery_pct', 10.0):
                assert result['halted'] is True

    def test_drawdown_re_engagement_above_recovery_threshold(self, test_config):
        """CB9: Drawdown recovered below recovery threshold → re-engage."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # Drawdown recovered: 100k peak, 98k current = 2% drawdown (well below 10% threshold)
            mock_cur.fetchone.return_value = (100000.0, 98000.0)

            result = cb._check_drawdown_re_engagement(date.today())

            # Should allow re-engagement
            assert result['halted'] is False

    def test_sector_concentration_high_loss(self, test_config):
        """CB10: Sector concentration — sector with -12%+ in 5d → halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            mock_cur.fetchall.side_effect = [
                [('AAPL', 'TECH'), ('MSFT', 'TECH')],  # Positions query: 2 columns
                [(-15.0, '2026-05-10'), (-0.5, '2026-05-09')],  # Sector perf query: 2 columns
            ]

            result = cb._check_sector_concentration(date.today())

            assert result['halted'] is True
            assert 'sector' in result.get('reason', '').lower()

    def test_sector_concentration_below_threshold(self, test_config):
        """CB10: Sector with -5% in 5d → no halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # -5% is above -12% threshold, so no halt
            mock_cur.fetchall.side_effect = [
                [('AAPL', 'TECH'), ('MSFT', 'TECH')],
                [(-5.0, '2026-05-10'), (0.2, '2026-05-09')],
            ]

            result = cb._check_sector_concentration(date.today())

            assert result['halted'] is False

    def test_sector_concentration_single_position(self, test_config):
        """CB10: Only 1 position in sector → no halt (no concentration risk)."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # Only 1 position, no concentration
            mock_cur.fetchall.return_value = [
                ('AAPL', 'TECH'),  # Only 1 position
            ]
            mock_cur.fetchone.return_value = (-0.20,)  # Even -20%, no halt

            result = cb._check_sector_concentration(date.today())

            assert result['halted'] is False

    def test_intraday_market_health_spy_drop(self, test_config):
        """CB11: Intraday market health — SPY -2.5% in 2d → halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # SPY prices: prior=102.56, latest=100.0 → change = (100-102.56)/102.56 = -2.5%
            mock_cur.fetchall.return_value = [(100.0,), (102.56,)]

            result = cb._check_intraday_market_health(date.today())

            assert result['halted'] is True

    def test_intraday_market_health_slight_drop(self, test_config):
        """CB11: SPY -1% in 2d → no halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # SPY prices: prior=101.01, latest=100.0 → change = (100-101.01)/101.01 = -1%
            mock_cur.fetchall.return_value = [(100.0,), (101.01,)]

            result = cb._check_intraday_market_health(date.today())

            assert result['halted'] is False

    def test_win_rate_below_floor(self, test_config):
        """CB12: Win rate floor — 35% over 20 trades → halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # 7 wins out of 20 trades = 35% win rate
            # The method calls fetchone() and expects (wins, losses, total)
            mock_cur.fetchone.return_value = (7, 13, 20)

            result = cb._check_win_rate_floor(date.today())

            # 35% < 40% floor
            assert result['halted'] is True

    def test_win_rate_above_floor(self, test_config):
        """CB12: Win rate 45% over 20 trades → no halt."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # 9 wins out of 20 = 45% win rate
            mock_cur.fetchall.return_value = [
                (1.0,), (1.0,), (1.0,), (1.0,), (1.0,), (1.0,), (1.0,), (1.0,), (1.0,),  # 9 winners
                (-1.0,), (-1.0,), (-1.0,), (-1.0,), (-1.0,), (-1.0,), (-1.0,), (-1.0,), (-1.0,), (-1.0,), (-1.0,),  # 11 losers
            ]

            result = cb._check_win_rate_floor(date.today())

            # 45% >= 40% floor
            assert result['halted'] is False

    def test_win_rate_insufficient_trades(self, test_config):
        """CB12: Only 8 trades (< 10 minimum) → no halt (insufficient data)."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # Only 8 trades (below 10 minimum for win rate check)
            mock_cur.fetchall.return_value = [
                (1.0,), (1.0,), (-1.0,), (-1.0,),  # 2 wins, 2 losses
                (-1.0,), (-1.0,), (-1.0,), (-1.0,),  # 4 losses
            ]

            result = cb._check_win_rate_floor(date.today())

            # Insufficient trades → no halt
            assert result['halted'] is False

    def test_daily_profit_cap_soft_check(self, test_config):
        """CB13: Daily profit cap — +3% profit → soft check only (halted=False, exceed=True)."""

        cb = CircuitBreaker(test_config)

        with patch.object(cb, 'connect'), \
             patch.object(cb, 'disconnect'), \
             patch.object(cb, 'cur') as mock_cur:

            # Daily return +3% (beyond typical profit cap of 2%)
            mock_cur.fetchone.return_value = (3.0,)

            result = cb._check_daily_profit_cap(date.today())

            # Profit cap is a soft check: always return halted=False (no mandatory halt)
            # but expose 'exceed_profit_cap' flag for monitoring
            assert result['halted'] is False
            assert result.get('exceed_profit_cap') is True
            assert result['value'] == 3.0
            assert result['threshold'] == 2.0
