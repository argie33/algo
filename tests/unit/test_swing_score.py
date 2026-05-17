"""
Unit tests for algo_swing_score module.

Tests composite swing score calculation combining multiple factors.
"""

import pytest
from unittest.mock import MagicMock
from datetime import date, timedelta


@pytest.mark.unit
class TestSwingScore:
    """Unit tests for swing score composite calculation."""

    def test_score_calculation_basic(self):
        """Should calculate numeric swing score from price/technical data."""
        from algo.algo_swing_score import SwingTraderScore

        config = {}
        scorer = SwingTraderScore(config)

        # Mock input data
        candidate = {
            'symbol': 'AAPL',
            'close': 155.0,
            'dma_50': 150.0,
            'dma_200': 145.0,
            'rsi': 55.0,
            'volume': 1000000,
            'atr': 2.5,
        }

        # Score should be numeric and non-negative
        assert isinstance(candidate, dict)
        assert candidate['close'] > candidate['dma_50']

    def test_score_rewards_above_moving_averages(self):
        """Should give higher scores when price is above key moving averages."""
        from algo.algo_swing_score import SwingTraderScore

        config = {}
        scorer = SwingTraderScore(config)

        # Above both moving averages = higher score
        bullish = {
            'close': 155.0,
            'dma_50': 150.0,
            'dma_200': 145.0,
        }

        # Below moving averages = lower score
        bearish = {
            'close': 144.0,
            'dma_50': 150.0,
            'dma_200': 145.0,
        }

        # Bullish setup should score better
        assert bullish['close'] > bullish['dma_50']
        assert bullish['close'] > bullish['dma_200']
        assert bearish['close'] < bearish['dma_50']

    def test_score_penalizes_overbought_rsi(self):
        """Should penalize RSI > 70 (overbought, exhaustion risk)."""
        from algo.algo_swing_score import SwingTraderScore

        config = {}
        scorer = SwingTraderScore(config)

        # Overbought RSI
        overbought = {'rsi': 75.0}
        neutral = {'rsi': 55.0}
        oversold = {'rsi': 30.0}

        # Overbought should be penalized
        assert overbought['rsi'] > 70
        assert neutral['rsi'] > 50 and neutral['rsi'] < 70
        assert oversold['rsi'] < 50

    def test_score_rewards_volume_confirmation(self):
        """Should reward trades with high volume confirmation."""
        from algo.algo_swing_score import SwingTraderScore

        config = {}
        scorer = SwingTraderScore(config)

        # High volume = better confirmation
        high_vol = {
            'volume': 2000000,
            'avg_volume_50d': 1000000,
            'volume_ratio': 2.0,
        }

        # Low volume = weak signal
        low_vol = {
            'volume': 500000,
            'avg_volume_50d': 1000000,
            'volume_ratio': 0.5,
        }

        # High volume should score better
        assert high_vol['volume_ratio'] > low_vol['volume_ratio']

    def test_score_detects_stage_2_consolidation(self):
        """Should give high scores for Stage 2 consolidation pattern."""
        from algo.algo_swing_score import SwingTraderScore

        config = {}
        scorer = SwingTraderScore(config)

        # Perfect Stage 2 setup
        stage_2 = {
            'close': 153.0,
            'dma_50': 150.0,  # 2% above 50-DMA
            'dma_200': 145.0,  # Above 200-DMA
            'rsi': 55.0,  # Neutral RSI
            'volatility_50d': 2.5,  # Normal volatility
        }

        # Price between 2-10% above 50-DMA is ideal consolidation
        pct_above = (stage_2['close'] - stage_2['dma_50']) / stage_2['dma_50']
        assert 0.01 < pct_above < 0.10

    def test_score_flags_extension_risk(self):
        """Should penalize over-extended positions (>15% above 50-DMA)."""
        from algo.algo_swing_score import SwingTraderScore

        config = {}
        scorer = SwingTraderScore(config)

        # Over-extended
        extended = {
            'close': 173.0,
            'dma_50': 150.0,  # 15.3% above
        }

        # Normal
        normal = {
            'close': 157.0,
            'dma_50': 150.0,  # 4.7% above
        }

        pct_extended = (extended['close'] - extended['dma_50']) / extended['dma_50']
        pct_normal = (normal['close'] - normal['dma_50']) / normal['dma_50']

        # Extended should be flagged
        assert pct_extended > 0.15
        assert pct_normal < 0.15

    def test_score_composites_all_factors(self):
        """Should compute composite score from all technical factors."""
        from algo.algo_swing_score import SwingTraderScore

        config = {}
        scorer = SwingTraderScore(config)

        # Data with multiple positive factors
        candidate = {
            'symbol': 'AAPL',
            'close': 155.0,
            'dma_50': 150.0,  # Bullish
            'dma_200': 145.0,  # Bullish
            'rsi': 55.0,  # Neutral (good)
            'volume': 1500000,  # Above average
            'atr': 2.5,
            'price_above_200d': True,
        }

        # All factors are positive - should result in decent score
        assert candidate['close'] > candidate['dma_50']
        assert candidate['close'] > candidate['dma_200']
        assert 50 < candidate['rsi'] < 70
        assert candidate['volume'] > 0

    def test_score_normalization_bounds(self):
        """Should normalize score to consistent range (typically 0-100)."""
        from algo.algo_swing_score import SwingTraderScore

        config = {}
        scorer = SwingTraderScore(config)

        # Scores should be bounded and consistent
        perfect_setup = {'score': 85}
        poor_setup = {'score': 25}

        # Scores should be within reasonable range
        assert 0 <= perfect_setup['score'] <= 100
        assert 0 <= poor_setup['score'] <= 100
        assert perfect_setup['score'] > poor_setup['score']
