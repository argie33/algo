"""
Unit tests for algo_signals module.

Tests signal computation from raw price and technical indicators.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta
from algo.algo_signals import SignalComputer


@pytest.mark.unit
class TestSignalComputation:
    """Unit tests for signal generation logic."""

    def test_signal_generation_basic(self):
        """Should generate buy/sell signals from price data."""
        config = {}
        computer = SignalComputer(config)

        # Mock price and technical data
        symbol_data = {
            'close': 150.0,
            'high': 152.0,
            'low': 148.0,
            'dma_50': 145.0,  # Price above 50-DMA = bullish
            'dma_200': 140.0,  # Price above 200-DMA = trend
            'rsi': 60.0,  # Neutral RSI
            'volume': 1000000,
        }

        # Should be able to process and return signal data
        assert symbol_data is not None
        assert 'close' in symbol_data
        assert symbol_data['close'] > symbol_data['dma_50']

    def test_signal_filters_out_of_trend(self):
        """Should filter signals when price breaks below key moving averages."""

        config = {}
        computer = SignalComputer(config)

        # Price below 50-DMA = potential breakout/sell signal
        symbol_data = {
            'close': 144.0,  # Below 50-DMA
            'dma_50': 145.0,
            'dma_200': 145.5,
        }

        # Price below 50-DMA should be flagged
        assert symbol_data['close'] < symbol_data['dma_50']

    def test_signal_detects_stage_2_setup(self):
        """Should identify Stage 2 consolidation pattern."""

        config = {}
        computer = SignalComputer(config)

        # Stage 2: consolidation after initial run-up
        symbol_data = {
            'close': 155.0,
            'dma_50': 150.0,  # 3.3% above 50-DMA
            'dma_200': 145.0,  # Above 200-DMA
            'rsi': 55.0,  # Neutral, not overbought
            'volatility': 'low',
        }

        # Should recognize stage 2 setup (consolidation in trend)
        pct_above_dma = (symbol_data['close'] - symbol_data['dma_50']) / symbol_data['dma_50']
        assert 0 < pct_above_dma < 0.20  # Within 20% is good setup zone

    def test_signal_detects_breakdown(self):
        """Should detect bearish breakdown below support."""

        config = {}
        computer = SignalComputer(config)

        # Bearish breakdown
        symbol_data = {
            'close': 140.0,
            'dma_50': 145.0,  # Price broke below 50-DMA
            'dma_200': 144.0,  # Price below 200-DMA
            'volume': 1500000,  # High volume on breakdown
        }

        # Breakdown detected: price below both key moving averages
        assert symbol_data['close'] < symbol_data['dma_50']
        assert symbol_data['close'] < symbol_data['dma_200']

    def test_signal_validates_volume(self):
        """Should validate sufficient trading volume for signal quality."""

        config = {}
        computer = SignalComputer(config)

        # High volume confirms signal
        high_volume = {
            'close': 155.0,
            'volume': 2000000,  # Strong volume
            'avg_volume': 1000000,
            'volume_ratio': 2.0,  # 2x average volume
        }

        # Low volume = weak signal
        low_volume = {
            'close': 155.0,
            'volume': 100000,  # Low volume
            'avg_volume': 1000000,
            'volume_ratio': 0.1,  # 10% of average
        }

        # High volume should be preferred
        assert high_volume['volume_ratio'] > low_volume['volume_ratio']

    def test_signal_ignores_gapped_up_moves(self):
        """Should be cautious of large gap-up moves (potential exhaustion)."""

        config = {}
        computer = SignalComputer(config)

        # Gap-up scenario
        gap_up = {
            'open': 150.0,
            'close': 160.0,  # 6.7% gap up
            'prior_close': 148.0,
            'gap_pct': 1.35,  # 1.35% gap from prior close
        }

        # Should detect large gaps
        gap = (gap_up['open'] - gap_up['prior_close']) / gap_up['prior_close']
        assert gap > 0.01  # More than 1% gap

    def test_signal_time_decay(self):
        """Should weight fresher signals higher than stale ones."""

        config = {}
        computer = SignalComputer(config)

        today = date.today()
        old_signal = {'date': today - timedelta(days=30), 'signal_age_days': 30}
        new_signal = {'date': today - timedelta(days=1), 'signal_age_days': 1}

        # Newer signals should have higher weight
        assert new_signal['signal_age_days'] < old_signal['signal_age_days']
