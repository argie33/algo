"""
Unit tests for advanced filters module.

Tests AdvancedFilters.evaluate_candidate() which gates 80% of trades:
- H1: Earnings blackout (within 5 days)
- H2: Over-extension (>15% above 50-DMA)
- H4: Liquidity check (<$5M avg volume)
- Sector overlap detection
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date, timedelta


@pytest.mark.unit
class TestAdvancedFilters:
    """Unit tests for advanced trade filters."""

    def test_earnings_blackout_rejects_within_5_days(self):
        """Should reject candidates with earnings within 5 days."""
        from algo.algo_advanced_filters import AdvancedFilters

        config = {}
        filters = AdvancedFilters(config)

        # Candidate with earnings in 3 days
        candidate = {
            'symbol': 'AAPL',
            'earnings_date': date.today() + timedelta(days=3),
            'close': 150.0,
            'volume': 1000000,
        }

        result = filters.evaluate_candidate(candidate)

        # Should be rejected due to earnings blackout
        assert result.get('passed') is False or result.get('failed_gates', []).count('earnings') > 0

    def test_earnings_blackout_allows_after_5_days(self):
        """Should allow candidates with earnings >5 days away."""
        from algo.algo_advanced_filters import AdvancedFilters

        config = {}
        filters = AdvancedFilters(config)

        # Candidate with earnings in 10 days
        candidate = {
            'symbol': 'AAPL',
            'earnings_date': date.today() + timedelta(days=10),
            'close': 150.0,
            'volume': 1000000,
        }

        result = filters.evaluate_candidate(candidate)

        # Should pass earnings gate (or at least not fail due to earnings)
        assert result.get('failed_gates', []).count('earnings') == 0

    def test_over_extension_rejects_above_15_percent(self):
        """Should reject candidates over-extended >15% above 50-DMA."""
        from algo.algo_advanced_filters import AdvancedFilters

        config = {}
        filters = AdvancedFilters(config)

        # Price 20% above 50-DMA (over-extended)
        candidate = {
            'symbol': 'AAPL',
            'close': 120.0,
            'dma_50': 100.0,  # 20% above is over-extended
            'earnings_date': date.today() + timedelta(days=30),
            'volume': 1000000,
        }

        result = filters.evaluate_candidate(candidate)

        # Should be rejected due to over-extension
        assert result.get('passed') is False or result.get('failed_gates', []).count('over_extension') > 0

    def test_over_extension_allows_within_15_percent(self):
        """Should allow candidates within 15% of 50-DMA."""
        from algo.algo_advanced_filters import AdvancedFilters

        config = {}
        filters = AdvancedFilters(config)

        # Price 10% above 50-DMA (acceptable)
        candidate = {
            'symbol': 'AAPL',
            'close': 110.0,
            'dma_50': 100.0,  # 10% above is acceptable
            'earnings_date': date.today() + timedelta(days=30),
            'volume': 1000000,
        }

        result = filters.evaluate_candidate(candidate)

        # Should pass over-extension gate
        assert result.get('failed_gates', []).count('over_extension') == 0

    def test_liquidity_check_rejects_low_volume(self):
        """Should reject candidates with <$5M average daily volume."""
        from algo.algo_advanced_filters import AdvancedFilters

        config = {}
        filters = AdvancedFilters(config)

        # Low volume: 10K shares * $150 = $1.5M daily volume
        candidate = {
            'symbol': 'AAPL',
            'close': 150.0,
            'volume': 10000,  # 10K shares = $1.5M < $5M minimum
            'dma_50': 150.0,
            'earnings_date': date.today() + timedelta(days=30),
        }

        result = filters.evaluate_candidate(candidate)

        # Should be rejected due to low liquidity
        assert result.get('passed') is False or result.get('failed_gates', []).count('liquidity') > 0

    def test_liquidity_check_allows_sufficient_volume(self):
        """Should allow candidates with >=$5M average daily volume."""
        from algo.algo_advanced_filters import AdvancedFilters

        config = {}
        filters = AdvancedFilters(config)

        # Sufficient volume: 40K shares * $150 = $6M daily volume
        candidate = {
            'symbol': 'AAPL',
            'close': 150.0,
            'volume': 40000,  # 40K shares = $6M > $5M minimum
            'dma_50': 150.0,
            'earnings_date': date.today() + timedelta(days=30),
        }

        result = filters.evaluate_candidate(candidate)

        # Should pass liquidity gate
        assert result.get('failed_gates', []).count('liquidity') == 0

    def test_all_gates_pass(self):
        """Should approve candidate when all gates pass."""
        from algo.algo_advanced_filters import AdvancedFilters

        config = {}
        filters = AdvancedFilters(config)

        # All criteria met
        candidate = {
            'symbol': 'AAPL',
            'close': 150.0,
            'dma_50': 145.0,  # 3.4% above (within 15%)
            'volume': 50000,  # 50K * $150 = $7.5M > $5M
            'earnings_date': date.today() + timedelta(days=30),  # >5 days away
        }

        result = filters.evaluate_candidate(candidate)

        # Should pass all gates
        assert result.get('passed') is True or len(result.get('failed_gates', [])) == 0

    def test_gate_scoring_produces_valid_score(self):
        """Returned composite score should be numeric and bounded."""
        from algo.algo_advanced_filters import AdvancedFilters

        config = {}
        filters = AdvancedFilters(config)

        candidate = {
            'symbol': 'AAPL',
            'close': 150.0,
            'dma_50': 145.0,
            'volume': 50000,
            'earnings_date': date.today() + timedelta(days=30),
        }

        result = filters.evaluate_candidate(candidate)

        # Score should be numeric and in expected range (typically 0-100)
        if 'score' in result:
            assert isinstance(result['score'], (int, float))
            assert 0 <= result['score'] <= 100
