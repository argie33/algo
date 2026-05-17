"""
C5: AdvancedFilters Hard-Fail Gates Unit Tests

Tests the four hard-fail gates that block obvious mistakes:
- H1: Earnings within block window (default <= 5 days)
- H2: Over-extended above 50-DMA (default > 15%)
- H4: Insufficient liquidity (avg $volume < min, default $5M)
- H5: Strong sector requirement (configurable, default off)
"""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, date as _date, timedelta
import os


from algo.algo_advanced_filters import AdvancedFilters


class TestHardFailGateEarnings:
    """Test H1: Earnings within block window gate."""

    @pytest.fixture
    def config(self):
        return {
            'block_days_before_earnings': 5,
            'max_extension_above_50ma_pct': 15.0,
            'min_avg_daily_dollar_volume': 5_000_000,
            'require_strong_sector': False,
        }

    @pytest.fixture
    def advanced_filters(self, config):
        filters = AdvancedFilters(config)
        filters.cur = MagicMock()
        filters._strong_sectors = {}
        filters._strong_industries = {}
        return filters

    def test_earnings_far_in_future_passes(self, advanced_filters):
        """VERIFY: Trade passes when earnings are far in future (>5 days)."""
        # Mock earnings at 20 days out
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "Should pass when earnings > 5 days away"
        assert 'Earnings' not in result['reason']

    def test_earnings_within_block_window_blocks(self, advanced_filters):
        """VERIFY: Trade blocked when earnings within default 5-day window."""
        # Mock earnings at 3 days out
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=3)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is False, "Should block when earnings within window"
        assert 'Earnings' in result['reason'], "Reason should mention earnings"
        assert '3' in result['reason'], "Should show days to earnings"

    def test_earnings_exactly_at_boundary_blocks(self, advanced_filters):
        """VERIFY: Earnings exactly at boundary (5 days) blocks."""
        # Mock earnings at exactly 5 days (boundary)
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=5)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is False, "Should block at boundary (5 days)"

    def test_earnings_zero_days_blocks(self, advanced_filters):
        """VERIFY: Today earnings blocks (0 days to earnings)."""
        # Earnings today
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=0)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is False, "Should block when earnings today"

    def test_earnings_none_passes(self, advanced_filters):
        """VERIFY: No earnings data available = pass (graceful degradation)."""
        # None earnings value (unknown when earnings are)
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=None)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "Unknown earnings should not block"

    def test_earnings_custom_block_window(self, advanced_filters):
        """VERIFY: Custom block window is respected."""
        # Change block window to 10 days
        advanced_filters.config['block_days_before_earnings'] = 10
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=7)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is False, "Should respect custom 10-day window"


class TestHardFailGateExtension:
    """Test H2: Over-extended above 50-DMA gate."""

    @pytest.fixture
    def config(self):
        return {
            'block_days_before_earnings': 5,
            'max_extension_above_50ma_pct': 15.0,
            'min_avg_daily_dollar_volume': 5_000_000,
            'require_strong_sector': False,
        }

    @pytest.fixture
    def advanced_filters(self, config):
        filters = AdvancedFilters(config)
        filters.cur = MagicMock()
        filters._strong_sectors = {}
        filters._strong_industries = {}
        return filters

    def test_extension_within_limit_passes(self, advanced_filters):
        """VERIFY: Trade passes when extension <= 15%."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=12.5)  # 12.5% < 15%
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "Should pass when extension <= limit"

    def test_extension_exceeds_limit_blocks(self, advanced_filters):
        """VERIFY: Trade blocked when extension > 15%."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=18.5)  # 18.5% > 15%
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is False, "Should block when extension > limit"
        assert 'above' in result['reason'].lower() or 'extended' in result['reason'].lower(), "Reason should mention extension"
        assert '18.5' in result['reason'], "Should show actual extension %"

    def test_extension_at_boundary_passes(self, advanced_filters):
        """VERIFY: Extension exactly at limit (15%) passes."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=15.0)  # Exactly at limit
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "Should pass at boundary"

    def test_extension_none_passes(self, advanced_filters):
        """VERIFY: Missing extension data = pass (graceful degradation)."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=None)  # No data
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "Unknown extension should not block"

    def test_extension_custom_limit(self, advanced_filters):
        """VERIFY: Custom max extension limit is respected."""
        advanced_filters.config['max_extension_above_50ma_pct'] = 10.0  # Custom: 10% instead of 15%
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=12.0)  # 12% > 10% custom limit
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is False, "Should respect custom extension limit"

    def test_extension_zero_passes(self, advanced_filters):
        """VERIFY: No extension (0%) passes."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=0.0)  # At 50-DMA exactly
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "Zero extension should pass"


class TestHardFailGateLiquidity:
    """Test H4: Insufficient liquidity gate."""

    @pytest.fixture
    def config(self):
        return {
            'block_days_before_earnings': 5,
            'max_extension_above_50ma_pct': 15.0,
            'min_avg_daily_dollar_volume': 5_000_000,
            'require_strong_sector': False,
        }

    @pytest.fixture
    def advanced_filters(self, config):
        filters = AdvancedFilters(config)
        filters.cur = MagicMock()
        filters._strong_sectors = {}
        filters._strong_industries = {}
        return filters

    def test_sufficient_liquidity_passes(self, advanced_filters):
        """VERIFY: Trade passes when avg volume >= $5M."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=6_000_000)  # > $5M

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "Should pass when volume >= $5M"

    def test_insufficient_liquidity_blocks(self, advanced_filters):
        """VERIFY: Trade blocked when avg volume < $5M."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=3_000_000)  # < $5M

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is False, "Should block when volume < $5M"
        assert 'Liquidity' in result['reason'], "Reason should mention liquidity"
        assert '$3.0M' in result['reason'] or '3' in result['reason'], "Should show actual volume"

    def test_liquidity_at_boundary_passes(self, advanced_filters):
        """VERIFY: Liquidity exactly at minimum threshold passes."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=5_000_000)  # Exactly $5M

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "Should pass at boundary ($5M)"

    def test_liquidity_none_passes(self, advanced_filters):
        """VERIFY: Missing liquidity data = pass (graceful degradation)."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=None)  # No data

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "Unknown liquidity should not block"

    def test_liquidity_custom_minimum(self, advanced_filters):
        """VERIFY: Custom liquidity minimum is respected."""
        advanced_filters.config['min_avg_daily_dollar_volume'] = 10_000_000  # $10M instead of $5M
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=7_000_000)  # > $5M but < $10M

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is False, "Should respect custom $10M minimum"

    def test_very_liquid_stock_passes(self, advanced_filters):
        """VERIFY: Very liquid stock (mega-cap) passes with high volume."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=500_000_000)  # $500M volume

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0, sector=None, industry=None)

        assert result['pass'] is True, "High-liquidity stocks should pass"


class TestHardFailGateSector:
    """Test H5: Strong sector requirement gate."""

    @pytest.fixture
    def config(self):
        return {
            'block_days_before_earnings': 5,
            'max_extension_above_50ma_pct': 15.0,
            'min_avg_daily_dollar_volume': 5_000_000,
            'require_strong_sector': False,  # Disabled by default
        }

    @pytest.fixture
    def advanced_filters(self, config):
        filters = AdvancedFilters(config)
        filters.cur = MagicMock()
        filters._strong_sectors = {'Technology': 70, 'Healthcare': 65, 'Financials': 60}
        filters._strong_industries = {'Cloud Computing': 85}
        return filters

    def test_sector_gate_disabled_by_default(self, advanced_filters):
        """VERIFY: Sector gate is disabled by default (config = False)."""
        # Even if sector is weak, should pass because gate is disabled
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0,
                                          sector='Utilities', industry=None)  # Weak sector

        assert result['pass'] is True, "Should pass when sector gate disabled"

    def test_strong_sector_passes_when_enabled(self, advanced_filters):
        """VERIFY: Stock in strong sector passes when gate enabled."""
        advanced_filters.config['require_strong_sector'] = True
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0,
                                          sector='Technology', industry=None)  # Strong sector

        assert result['pass'] is True, "Should pass for strong sector when gate enabled"

    def test_weak_sector_blocks_when_enabled(self, advanced_filters):
        """VERIFY: Stock in weak sector blocked when gate enabled."""
        advanced_filters.config['require_strong_sector'] = True
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('CORP', _date.today(), 50.0,
                                          sector='Utilities', industry=None)  # Not in strong list

        assert result['pass'] is False, "Should block weak sector when gate enabled"
        assert 'Sector' in result['reason'], "Reason should mention sector"

    def test_null_sector_with_gate_enabled(self, advanced_filters):
        """VERIFY: Null/None sector passes when gate enabled (sector check requires non-null).

        Note: The implementation checks 'if sector and sector not in...', so None sectors
        are treated as missing data and allowed to pass (graceful degradation).
        """
        advanced_filters.config['require_strong_sector'] = True
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        result = advanced_filters.evaluate_candidate('UNKNOWN', _date.today(), 50.0,
                                          sector=None, industry=None)

        # None sector: gate doesn't apply to unknown sectors (graceful degradation)
        assert result['pass'] is True, "None sector passes (no sector data to validate)"

    def test_multiple_strong_sectors_recognized(self, advanced_filters):
        """VERIFY: All configured strong sectors are recognized."""
        advanced_filters.config['require_strong_sector'] = True
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=20)
        advanced_filters._extension_pct = MagicMock(return_value=10.0)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=10_000_000)

        for sector in ['Technology', 'Healthcare', 'Financials']:
            result = advanced_filters.evaluate_candidate('TEST', _date.today(), 50.0,
                                              sector=sector, industry=None)
            assert result['pass'] is True, f"Should pass for {sector} when in strong list"


class TestHardFailGatesIntegration:
    """Integration tests: multiple gates interacting."""

    @pytest.fixture
    def config(self):
        return {
            'block_days_before_earnings': 5,
            'max_extension_above_50ma_pct': 15.0,
            'min_avg_daily_dollar_volume': 5_000_000,
            'require_strong_sector': False,
        }

    @pytest.fixture
    def advanced_filters(self, config):
        filters = AdvancedFilters(config)
        filters.cur = MagicMock()
        filters._strong_sectors = {'Technology': 70}
        filters._strong_industries = {}
        return filters

    def test_all_gates_pass_together(self, advanced_filters):
        """VERIFY: Stock passes when all gates are satisfied."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=30)  # > 5d
        advanced_filters._extension_pct = MagicMock(return_value=10.0)  # < 15%
        advanced_filters._avg_dollar_volume = MagicMock(return_value=8_000_000)  # > $5M

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0,
                                          sector='Technology', industry=None)

        assert result['pass'] is True, "Should pass when all gates pass"

    def test_earnings_failure_alone_blocks(self, advanced_filters):
        """VERIFY: Failed earnings gate blocks even if other gates pass."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=2)  # < 5d
        advanced_filters._extension_pct = MagicMock(return_value=10.0)  # < 15%
        advanced_filters._avg_dollar_volume = MagicMock(return_value=8_000_000)  # > $5M

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0,
                                          sector='Technology', industry=None)

        assert result['pass'] is False, "Failed earnings gate should block"

    def test_extension_failure_alone_blocks(self, advanced_filters):
        """VERIFY: Failed extension gate blocks even if other gates pass."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=30)  # > 5d
        advanced_filters._extension_pct = MagicMock(return_value=20.0)  # > 15%
        advanced_filters._avg_dollar_volume = MagicMock(return_value=8_000_000)  # > $5M

        result = advanced_filters.evaluate_candidate('AAPL', _date.today(), 150.0,
                                          sector='Technology', industry=None)

        assert result['pass'] is False, "Failed extension gate should block"

    def test_liquidity_failure_alone_blocks(self, advanced_filters):
        """VERIFY: Failed liquidity gate blocks even if other gates pass."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=30)  # > 5d
        advanced_filters._extension_pct = MagicMock(return_value=10.0)  # < 15%
        advanced_filters._avg_dollar_volume = MagicMock(return_value=2_000_000)  # < $5M

        result = advanced_filters.evaluate_candidate('MICRO', _date.today(), 50.0,
                                          sector='Technology', industry=None)

        assert result['pass'] is False, "Failed liquidity gate should block"

    def test_first_failure_reported(self, advanced_filters):
        """VERIFY: If multiple gates fail, at least one is reported in reason."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=2)  # FAILS
        advanced_filters._extension_pct = MagicMock(return_value=20.0)  # FAILS
        advanced_filters._avg_dollar_volume = MagicMock(return_value=2_000_000)  # FAILS

        result = advanced_filters.evaluate_candidate('BAD', _date.today(), 50.0,
                                          sector=None, industry=None)

        assert result['pass'] is False, "Should fail"
        # At least one failure reason should be in the report
        assert result['reason'] is not None
        assert len(result['reason']) > 0


class TestHardFailGatesEdgeCases:
    """Edge cases in hard-fail gate logic."""

    @pytest.fixture
    def config(self):
        return {
            'block_days_before_earnings': 5,
            'max_extension_above_50ma_pct': 15.0,
            'min_avg_daily_dollar_volume': 5_000_000,
            'require_strong_sector': False,
        }

    @pytest.fixture
    def advanced_filters(self, config):
        filters = AdvancedFilters(config)
        filters.cur = MagicMock()
        filters._strong_sectors = {}
        filters._strong_industries = {}
        return filters

    def test_all_data_missing_passes(self, advanced_filters):
        """VERIFY: Missing all data defaults to pass (graceful degradation)."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=None)
        advanced_filters._extension_pct = MagicMock(return_value=None)
        advanced_filters._avg_dollar_volume = MagicMock(return_value=None)

        result = advanced_filters.evaluate_candidate('UNKNOWN', _date.today(), 50.0,
                                          sector=None, industry=None)

        # All None values should not block — graceful degradation
        assert result['pass'] is True, "Should pass when all data missing"

    def test_negative_values_handled(self, advanced_filters):
        """VERIFY: Negative values handled correctly (shouldn't happen but safeguard)."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=-5)  # Invalid
        advanced_filters._extension_pct = MagicMock(return_value=-2.0)  # Invalid
        advanced_filters._avg_dollar_volume = MagicMock(return_value=-1_000_000)  # Invalid

        try:
            result = advanced_filters.evaluate_candidate('BAD', _date.today(), 50.0,
                                              sector=None, industry=None)
            # Should handle gracefully without crashing
            assert isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"Should handle negative values gracefully: {e}")

    def test_zero_values_handled(self, advanced_filters):
        """VERIFY: Zero values handled correctly."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=0)  # Earnings today
        advanced_filters._extension_pct = MagicMock(return_value=0.0)  # At 50-DMA
        advanced_filters._avg_dollar_volume = MagicMock(return_value=0)  # No volume

        result = advanced_filters.evaluate_candidate('TEST', _date.today(), 50.0,
                                          sector=None, industry=None)

        # Earnings today should block
        assert result['pass'] is False

    def test_very_large_values_handled(self, advanced_filters):
        """VERIFY: Very large values (mega-cap stocks) handled correctly."""
        advanced_filters._estimate_days_to_earnings = MagicMock(return_value=100)
        advanced_filters._extension_pct = MagicMock(return_value=50.0)  # 50% extended — FAILS
        advanced_filters._avg_dollar_volume = MagicMock(return_value=1_000_000_000)  # $1B volume

        result = advanced_filters.evaluate_candidate('MEGA', _date.today(), 300.0,
                                          sector=None, industry=None)

        assert result['pass'] is False, "Extension should fail even at scale"
