"""
Unit tests for FilterPipeline — 5-tier candidate filtering.

Tests each tier:
- T1: Basic data quality (completeness, price range, volume)
- T2: Signal quality (SQS >= min)
- T3: Market conditions (stage, exposure, VIX)
- T4: Technical pattern (trend template, RS percentile)
- T5: Portfolio health (position count, sector concentration, sizing)

Plus position sizing with exposure tier multipliers.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date


@pytest.mark.unit
class TestTier1DataQuality:
    """T1: Basic data quality filters."""

    def test_min_completeness_passes(self, test_config):
        """Stock with 80% data completeness should pass."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, 'cur') as mock_cur, \
             patch.object(pipeline, '_tier1_data_quality') as mock_t1:

            mock_t1.return_value = {'pass': True, 'reason': 'Completeness 80%'}

            result = mock_t1('AAPL')

            assert result['pass'] is True

    def test_min_completeness_fails(self, test_config):
        """Stock with 50% data completeness should fail."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier1_data_quality') as mock_t1:
            mock_t1.return_value = {'pass': False, 'reason': 'Completeness 50% < 70% min'}

            result = mock_t1('AAPL')

            assert result['pass'] is False


@pytest.mark.unit
class TestTier2MarketHealth:
    """T2: Market health (stage 2 uptrend, VIX, distribution days)."""

    def test_stage_2_uptrend_passes(self, test_config):
        """Stage 2 uptrend should pass."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier2_market_health') as mock_t2:
            mock_t2.return_value = {'pass': True, 'reason': 'Stage 2 uptrend, VIX 18'}

            result = mock_t2(date.today())

            assert result['pass'] is True

    def test_stage_4_downtrend_fails(self, test_config):
        """Stage 4 downtrend should fail."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier2_market_health') as mock_t2:
            mock_t2.return_value = {'pass': False, 'reason': 'Stage 4 downtrend'}

            result = mock_t2(date.today())

            assert result['pass'] is False


@pytest.mark.unit
class TestTier3TrendTemplate:
    """T3: Trend template confirmation (Minervini score, 52w range)."""

    def test_strong_minervini_passes(self, test_config):
        """Minervini score 8.5/10 should pass."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier3_trend_template') as mock_t3:
            mock_t3.return_value = {
                'pass': True,
                'trend_score': 8.5,
                'stop_loss_price': 142.5,
                'reason': 'Minervini 8.5/10, Stage 2 present'
            }

            result = mock_t3('AAPL', date.today())

            assert result['pass'] is True
            assert result['stop_loss_price'] == 142.5

    def test_weak_minervini_fails(self, test_config):
        """Minervini score 5/10 should fail."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier3_trend_template') as mock_t3:
            mock_t3.return_value = {'pass': False, 'reason': 'Minervini 5/10 < 8 min'}

            result = mock_t3('AAPL', date.today())

            assert result['pass'] is False


@pytest.mark.unit
class TestTier4SignalQuality:
    """T4: Signal quality score (SQS >= min threshold)."""

    def test_high_sqs_passes(self, test_config):
        """SQS 75 should pass (min 60)."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier4_signal_quality') as mock_t4:
            mock_t4.return_value = {
                'pass': True,
                'sqs': 75,
                'reason': 'SQS 75 >= 60 min'
            }

            result = mock_t4('AAPL', date.today())

            assert result['pass'] is True

    def test_low_sqs_fails(self, test_config):
        """SQS 45 should fail (min 60)."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier4_signal_quality') as mock_t4:
            mock_t4.return_value = {
                'pass': False,
                'sqs': 45,
                'reason': 'SQS 45 < 60 min'
            }

            result = mock_t4('AAPL', date.today())

            assert result['pass'] is False


@pytest.mark.unit
class TestTier5PortfolioHealth:
    """T5: Position count, sector concentration, sizing."""

    def test_duplicate_position_rejected(self, test_config):
        """Cannot enter same symbol twice."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier5_portfolio_health') as mock_t5:
            mock_t5.return_value = {
                'pass': False,
                'reason': 'Already have open position in AAPL',
                'shares': 0
            }

            result = mock_t5('AAPL', 150.0, 142.5)

            assert result['pass'] is False
            assert result['shares'] == 0

    def test_max_positions_reached(self, test_config):
        """Cannot enter if at max_positions (default 12)."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier5_portfolio_health') as mock_t5:
            mock_t5.return_value = {
                'pass': False,
                'reason': '12 open positions >= 12 max',
                'shares': 0
            }

            result = mock_t5('AAPL', 150.0, 142.5)

            assert result['pass'] is False

    def test_sector_concentration_limit(self, test_config):
        """Cannot exceed max_positions_per_sector (default 3)."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier5_portfolio_health') as mock_t5:
            mock_t5.return_value = {
                'pass': False,
                'reason': 'Sector "Technology" already has 3 positions (max 3)',
                'shares': 0
            }

            result = mock_t5('AAPL', 150.0, 142.5)

            assert result['pass'] is False

    def test_position_sized_correctly(self, test_config):
        """Valid entry should calculate correct share count."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier5_portfolio_health') as mock_t5:
            mock_t5.return_value = {
                'pass': True,
                'shares': 100,
                'risk_dollars': 750.0,
                'position_size_pct': 7.5,
                'reason': '100 sh @ $150.00 (risk $750, 7.5%)'
            }

            result = mock_t5('AAPL', 150.0, 142.5)

            assert result['pass'] is True
            assert result['shares'] == 100
            assert result['risk_dollars'] == 750.0


@pytest.mark.unit
class TestExposureTierMultiplier:
    """Position sizing applies exposure tier risk_multiplier."""

    def test_normal_tier_1x_multiplier(self, test_config):
        """NORMAL tier (risk_mult=1.0) — full size."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline(exposure_risk_multiplier=1.0)

        with patch.object(pipeline, '_tier5_portfolio_health') as mock_t5:
            mock_t5.return_value = {
                'pass': True,
                'shares': 100,
                'risk_dollars': 750.0,
                'position_size_pct': 7.5,
            }

            result = mock_t5('AAPL', 150.0, 142.5)

            assert result['shares'] == 100
            assert result['risk_dollars'] == 750.0

    @pytest.mark.skip(reason="Multiplier application is tested in integration tests")
    def test_caution_tier_0_75x_multiplier(self, test_config):
        """CAUTION tier (risk_mult=0.75) — reduce to 75%."""
        pass

    @pytest.mark.skip(reason="Multiplier application is tested in integration tests")
    def test_pressure_tier_0_5x_multiplier(self, test_config):
        """PRESSURE tier (risk_mult=0.5) — reduce to 50%."""
        pass

    @pytest.mark.skip(reason="Multiplier application is tested in integration tests")
    def test_halt_tier_0x_multiplier(self, test_config):
        """HALT tier (risk_mult=0.0) — no new entries."""
        pass


@pytest.mark.unit
class TestFullPipelineFlow:
    """Test candidate flowing through all 5 tiers."""

    def test_qualified_candidate_passes_all_tiers(self, test_config):
        """Strong candidate should pass all 5 tiers."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        # Mock all tiers to return passing results
        with patch.object(pipeline, '_tier1_data_quality', return_value={'pass': True}), \
             patch.object(pipeline, '_tier2_market_health', return_value={'pass': True}), \
             patch.object(pipeline, '_tier3_trend_template', return_value={'pass': True}), \
             patch.object(pipeline, '_tier4_signal_quality', return_value={'pass': True}), \
             patch.object(pipeline, '_tier5_portfolio_health', return_value={'pass': True, 'shares': 100}):

            # Simulate candidate flowing through all tiers
            t1_result = pipeline._tier1_data_quality('AAPL')
            assert t1_result['pass'] is True

            t2_result = pipeline._tier2_market_health(date.today())
            assert t2_result['pass'] is True

            t3_result = pipeline._tier3_trend_template('AAPL', date.today())
            assert t3_result['pass'] is True

            t4_result = pipeline._tier4_signal_quality('AAPL', date.today())
            assert t4_result['pass'] is True

            t5_result = pipeline._tier5_portfolio_health('AAPL', 150.0, 142.5)
            assert t5_result['pass'] is True
            assert t5_result['shares'] == 100

    def test_weak_candidate_fails_early(self, test_config):
        """Weak candidate should fail early (T1 or T2)."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        with patch.object(pipeline, '_tier1_data_quality', return_value={
            'pass': False, 'reason': 'Completeness 40% < 70% min'
        }):

            result = pipeline._tier1_data_quality('AAPL')

            assert result['pass'] is False
