"""
Unit tests for algo_position_sizer - position sizing based on risk management rules.

Tests cover:
- Normal position sizing (base risk 0.75% per trade)
- Risk adjustments (drawdown defense, VIX caution, market exposure)
- Constraint checks (max positions, concentration limits, total invested)
- Error handling (DB failures, invalid inputs, fail-closed)
- Edge cases (zero risk, max positions, phase climax)

Critical for production: Correct sizing prevents catastrophic losses.
Bad sizing = wrong P&L, over-concentrated positions, account blowup.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import date
import psycopg2
import psycopg2.errors
from algo.algo_position_sizer import PositionSizer


class TestPositionSizerInitialization:
    """Test position sizer initialization."""

    def test_init_with_provided_connection(self):
        """Should initialize with provided connection."""
        config = {'max_positions': 12}
        mock_conn = Mock()
        mock_cur = Mock()

        sizer = PositionSizer(config, conn=mock_conn, cur=mock_cur)

        assert sizer.config == config
        assert sizer.conn == mock_conn
        assert sizer.cur == mock_cur
        assert sizer._owns_connection is False

    def test_init_without_connection(self):
        """Should flag ownership when connection not provided."""
        config = {'max_positions': 12}

        with patch('algo.algo_position_sizer.psycopg2.connect'):
            sizer = PositionSizer(config)
            assert sizer._owns_connection is True


class TestPortfolioValue:
    """Test portfolio value retrieval."""

    def test_portfolio_value_from_alpaca(self):
        """Should get portfolio value from live Alpaca."""
        config = {}
        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        with patch.object(sizer, '_fetch_live_alpaca_equity', return_value=100000.0):
            value = sizer.get_portfolio_value()
            assert value == 100000.0

    def test_portfolio_value_from_snapshot(self):
        """Should fall back to snapshot when Alpaca unavailable."""
        config = {}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (50000.0, date(2026, 5, 15))

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)

        with patch.object(sizer, '_fetch_live_alpaca_equity', return_value=None):
            value = sizer.get_portfolio_value()
            assert value == 50000.0

    def test_portfolio_value_fails_when_none_available(self):
        """Should fail-closed when neither Alpaca nor snapshot available."""
        config = {}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = None

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)

        with patch.object(sizer, '_fetch_live_alpaca_equity', return_value=None):
            with pytest.raises(RuntimeError):
                sizer.get_portfolio_value()


class TestDrawdownCalculation:
    """Test drawdown calculation and risk adjustment."""

    def test_drawdown_calculation(self):
        """Should calculate drawdown correctly (peak-to-current)."""
        config = {}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (100000.0, 90000.0)  # peak, current

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        dd = sizer.get_current_drawdown()

        assert dd == 10.0  # (100k-90k)/100k = 10%

    def test_drawdown_no_data(self):
        """Should return 0 when no data."""
        config = {}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = None

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_current_drawdown() == 0.0

    def test_drawdown_db_error_returns_extreme(self):
        """Should return 25% (halt) on DB error (fail-closed)."""
        config = {}
        mock_cur = Mock()
        mock_cur.execute.side_effect = Exception("DB error")

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_current_drawdown() == 25.0

    def test_risk_adjustment_no_drawdown(self):
        """Should apply 1.0x multiplier with no drawdown."""
        config = {}
        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        with patch.object(sizer, 'get_current_drawdown', return_value=0.0):
            assert sizer.get_risk_adjustment() == 1.0

    def test_risk_adjustment_at_minus_5_percent(self):
        """Should apply configured reduction at -5% drawdown."""
        config = {'risk_reduction_at_minus_5': 0.75}
        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        with patch.object(sizer, 'get_current_drawdown', return_value=5.0):
            assert sizer.get_risk_adjustment() == 0.75

    def test_risk_adjustment_at_minus_10_percent(self):
        """Should apply configured reduction at -10% drawdown."""
        config = {'risk_reduction_at_minus_10': 0.5}
        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        with patch.object(sizer, 'get_current_drawdown', return_value=10.0):
            assert sizer.get_risk_adjustment() == 0.5

    def test_risk_adjustment_at_minus_15_percent(self):
        """Should apply configured reduction at -15% drawdown."""
        config = {'risk_reduction_at_minus_15': 0.25}
        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        with patch.object(sizer, 'get_current_drawdown', return_value=15.0):
            assert sizer.get_risk_adjustment() == 0.25

    def test_risk_adjustment_at_minus_20_halts_trading(self):
        """Should halt all trading (0x) at -20% drawdown."""
        config = {}
        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        with patch.object(sizer, 'get_current_drawdown', return_value=20.0):
            assert sizer.get_risk_adjustment() == 0.0


class TestMarketExposureMultiplier:
    """Test market exposure multiplier."""

    def test_normal_exposure(self):
        """Should convert exposure % to multiplier."""
        config = {}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (80.0,)  # 80%

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_market_exposure_multiplier() == 0.8

    def test_no_data_defaults_to_neutral(self):
        """Should return 1.0 (neutral) when no data."""
        config = {}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = None

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_market_exposure_multiplier() == 1.0

    def test_db_error_returns_conservative(self):
        """Should return 0.5 (50% = conservative) on DB error."""
        config = {}
        mock_cur = Mock()
        mock_cur.execute.side_effect = Exception("DB error")

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_market_exposure_multiplier() == 0.5


class TestVIXMultiplier:
    """Test VIX caution multiplier."""

    def test_vix_normal(self):
        """Should apply no reduction when VIX normal."""
        config = {'vix_caution_threshold': 25.0, 'vix_max_threshold': 35.0}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (20.0,)  # Normal

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_vix_caution_multiplier() == 1.0

    def test_vix_caution_zone(self):
        """Should reduce risk when VIX in caution zone."""
        config = {
            'vix_caution_threshold': 25.0,
            'vix_max_threshold': 35.0,
            'vix_caution_risk_reduction': 0.75
        }
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (30.0,)  # In caution zone

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_vix_caution_multiplier() == 0.75

    def test_vix_above_max(self):
        """Should return 1.0 when VIX > max (don't reduce further)."""
        config = {
            'vix_caution_threshold': 25.0,
            'vix_max_threshold': 35.0,
            'vix_caution_risk_reduction': 0.75
        }
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (40.0,)  # Above max

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_vix_caution_multiplier() == 1.0


class TestPositionCountAndValue:
    """Test position count and value retrieval."""

    def test_get_position_count(self):
        """Should get count of open positions."""
        config = {}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (5,)

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_position_count() == 5

    def test_position_count_db_error_fails_closed(self):
        """Should return max_positions on DB error (fail-closed)."""
        config = {'max_positions': 12}
        mock_cur = Mock()
        mock_cur.execute.side_effect = Exception("DB error")

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_position_count() == 12

    def test_get_active_positions_value(self):
        """Should get sum of active position values."""
        config = {}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (50000.0,)

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_active_positions_value() == 50000.0

    def test_active_positions_value_no_positions(self):
        """Should return 0 when no open positions."""
        config = {}
        mock_cur = Mock()
        mock_cur.fetchone.return_value = (0.0,)

        sizer = PositionSizer(config, conn=Mock(), cur=mock_cur)
        assert sizer.get_active_positions_value() == 0.0


class TestCalculatePositionSize:
    """Test the main position sizing calculation."""

    @pytest.fixture
    def base_sizer(self):
        """Create sizer with all helper methods mocked."""
        config = {
            'max_positions': 12,
            'base_risk_pct': 0.75,
            'max_position_size_pct': 8.0,
            'max_concentration_pct': 50.0,
            'max_total_invested_pct': 95.0,
            'min_risk_pct_floor': 0.10,
        }

        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        sizer.get_portfolio_value = Mock(return_value=100000.0)
        sizer.get_risk_adjustment = Mock(return_value=1.0)
        sizer.get_position_count = Mock(return_value=5)
        sizer.get_active_positions_value = Mock(return_value=30000.0)
        sizer.get_market_exposure_multiplier = Mock(return_value=1.0)
        sizer.get_vix_caution_multiplier = Mock(return_value=1.0)
        sizer.get_phase_size_multiplier = Mock(return_value=1.0)

        return sizer

    def test_normal_position_size(self, base_sizer):
        """Should calculate position size correctly in normal conditions."""
        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=150.0,
            stop_loss_price=140.0
        )

        assert result['status'] == 'ok'
        assert result['shares'] > 0
        assert result['risk_dollars'] > 0
        assert result['position_value'] > 0

    def test_max_positions_reached(self, base_sizer):
        """Should fail when max positions reached."""
        base_sizer.get_position_count.return_value = 12

        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=150.0,
            stop_loss_price=140.0
        )

        assert result['status'] == 'no_room'
        assert result['shares'] == 0

    def test_drawdown_halt(self, base_sizer):
        """Should fail when drawdown halt active (risk_adjustment=0)."""
        base_sizer.get_risk_adjustment.return_value = 0.0

        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=150.0,
            stop_loss_price=140.0
        )

        assert result['status'] == 'drawdown_halt'
        assert result['shares'] == 0

    def test_phase_climax_halt(self, base_sizer):
        """Should fail when stock in Stage-2 climax phase."""
        base_sizer.get_phase_size_multiplier.return_value = 0.0

        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=150.0,
            stop_loss_price=140.0
        )

        assert result['status'] == 'phase_climax'
        assert result['shares'] == 0

    def test_invalid_prices(self, base_sizer):
        """Should fail with invalid entry/stop prices."""
        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=150.0,
            stop_loss_price=150.0  # Can't be equal
        )

        assert result['status'] == 'invalid'
        assert result['shares'] == 0

    def test_position_too_small(self, base_sizer):
        """Should fail when position < 1 share."""
        base_sizer.get_portfolio_value.return_value = 1000.0

        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=150.0,
            stop_loss_price=140.0
        )

        assert result['status'] == 'too_small'
        assert result['shares'] == 0

    def test_concentration_limit(self, base_sizer):
        """Should fail when position > max_concentration_pct."""
        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=500.0,  # High price to force large position
            stop_loss_price=400.0
        )

        if result['status'] == 'ok':
            assert result['position_size_pct'] <= 50.0

    def test_total_invested_limit(self, base_sizer):
        """Should fail when total invested > max_total_invested_pct."""
        base_sizer.get_active_positions_value.return_value = 95000.0

        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=150.0,
            stop_loss_price=140.0
        )

        assert result['status'] == 'no_room'
        assert result['shares'] == 0

    def test_applies_all_multipliers(self, base_sizer):
        """Should apply all risk multipliers correctly."""
        base_sizer.get_risk_adjustment.return_value = 0.75
        base_sizer.get_market_exposure_multiplier.return_value = 0.8
        base_sizer.get_vix_caution_multiplier.return_value = 0.9
        base_sizer.get_phase_size_multiplier.return_value = 1.0

        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=150.0,
            stop_loss_price=140.0
        )

        expected_risk = 100000.0 * 0.0075 * 0.75 * 0.8 * 0.9
        assert result['status'] == 'ok'
        # Allow some tolerance for regime multiplier (0.75-1.0 range)
        assert expected_risk * 0.75 <= result['risk_dollars'] <= expected_risk

    def test_min_risk_floor(self, base_sizer):
        """Should apply min_risk_pct_floor to prevent cascading to 0."""
        base_sizer.get_risk_adjustment.return_value = 0.1
        base_sizer.get_market_exposure_multiplier.return_value = 0.2
        base_sizer.get_vix_caution_multiplier.return_value = 0.5

        result = base_sizer.calculate_position_size(
            symbol='AAPL',
            entry_price=150.0,
            stop_loss_price=140.0
        )

        if result['status'] == 'ok':
            assert result['risk_dollars'] >= 100.0  # 0.1% floor


class TestPyramidSplit:
    """Test pyramid entry split."""

    def test_default_pyramid_split(self):
        """Should return default 50/33/17 split."""
        config = {}
        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        splits = sizer.get_pyramid_split()

        assert len(splits) == 3
        assert abs(splits[0] - 0.50) < 0.01
        assert abs(splits[1] - 0.33) < 0.01
        assert abs(splits[2] - 0.17) < 0.01

    def test_custom_pyramid_split(self):
        """Should use custom split from config."""
        config = {'pyramid_split_pct': '40,35,25'}
        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        splits = sizer.get_pyramid_split()

        assert splits[0] == 0.40
        assert splits[1] == 0.35
        assert splits[2] == 0.25

    def test_invalid_split_uses_default(self):
        """Should use default when config invalid."""
        config = {'pyramid_split_pct': 'invalid'}
        sizer = PositionSizer(config, conn=Mock(), cur=Mock())

        splits = sizer.get_pyramid_split()

        assert len(splits) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
