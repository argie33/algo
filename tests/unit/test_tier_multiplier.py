"""
Unit tests for Tier Multiplier — exposure-based position sizing adjustment.

Tests the _apply_tier_multiplier method in FilterPipeline:
- NORMAL tier (1.0x): Full position size
- CAUTION tier (0.75x): 75% position size, reduced risk
- PRESSURE tier (0.5x): 50% position size, minimum size
- HALT tier (0.0x): No trading allowed

Verifies that multipliers are applied correctly based on market exposure tier.
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestTierMultiplier:
    """Test _apply_tier_multiplier method in FilterPipeline."""

    def test_normal_tier_1_0x_multiplier(self):
        """NORMAL tier applies 1.0x multiplier (full position size)."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()
        base_size = 1000.0
        result = pipeline._apply_tier_multiplier(base_size, 'NORMAL', 0.75)

        assert result == 1000.0, f"Expected 1000.0, got {result}"

    def test_caution_tier_0_75x_multiplier(self):
        """CAUTION tier applies 0.75x multiplier (75% position size)."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()
        base_size = 1000.0
        result = pipeline._apply_tier_multiplier(base_size, 'CAUTION', 0.75)

        expected = 1000.0 * 0.75
        assert result == pytest.approx(expected, rel=0.01), \
            f"Expected {expected}, got {result}"

    def test_pressure_tier_0_5x_multiplier(self):
        """PRESSURE tier applies 0.5x multiplier (50% position size)."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()
        base_size = 1000.0
        result = pipeline._apply_tier_multiplier(base_size, 'PRESSURE', 0.75)

        expected = 1000.0 * 0.5
        assert result == pytest.approx(expected, rel=0.01), \
            f"Expected {expected}, got {result}"

    def test_halt_tier_0_0x_multiplier(self):
        """HALT tier applies 0.0x multiplier (no trading allowed)."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()
        base_size = 1000.0
        result = pipeline._apply_tier_multiplier(base_size, 'HALT', 0.75)

        assert result == 0.0, f"Expected 0.0, got {result}"

    def test_unknown_tier_defaults_to_1_0x(self):
        """Unknown tier defaults to 1.0x multiplier."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()
        base_size = 1000.0
        result = pipeline._apply_tier_multiplier(base_size, 'UNKNOWN', 0.75)

        assert result == 1000.0, f"Expected 1000.0 for unknown tier, got {result}"

    def test_multiplier_with_zero_base_size(self):
        """Multiplier applied to zero base size returns zero."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()
        base_size = 0.0
        result = pipeline._apply_tier_multiplier(base_size, 'NORMAL', 0.75)

        assert result == 0.0, f"Expected 0.0, got {result}"

    def test_multiplier_with_decimal_base_size(self):
        """Multiplier handles decimal base sizes correctly."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()
        base_size = 1234.56
        result = pipeline._apply_tier_multiplier(base_size, 'CAUTION', 0.75)

        expected = 1234.56 * 0.75
        assert result == pytest.approx(expected, rel=0.01), \
            f"Expected {expected}, got {result}"

    def test_multiplier_cascade_risk_reduction(self):
        """Verify multiplier cascade reduces risk proportionally."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()
        base_size = 1000.0

        normal = pipeline._apply_tier_multiplier(base_size, 'NORMAL', 0.75)
        caution = pipeline._apply_tier_multiplier(base_size, 'CAUTION', 0.75)
        pressure = pipeline._apply_tier_multiplier(base_size, 'PRESSURE', 0.75)
        halt = pipeline._apply_tier_multiplier(base_size, 'HALT', 0.75)

        # Verify correct hierarchy
        assert normal > caution > pressure > halt, \
            f"Hierarchy violated: NORMAL={normal}, CAUTION={caution}, PRESSURE={pressure}, HALT={halt}"
        assert normal == 1000.0, f"NORMAL should be 1000.0, got {normal}"
        assert caution == pytest.approx(750.0, rel=0.01), f"CAUTION should be ~750.0, got {caution}"
        assert pressure == pytest.approx(500.0, rel=0.01), f"PRESSURE should be ~500.0, got {pressure}"
        assert halt == 0.0, f"HALT should be 0.0, got {halt}"

    def test_multiplier_applied_to_different_base_sizes(self):
        """Multiplier scales proportionally regardless of base size."""
        from algo_filter_pipeline import FilterPipeline

        pipeline = FilterPipeline()

        # Test with different base sizes
        test_sizes = [100.0, 500.0, 1000.0, 5000.0, 10000.0]

        for base_size in test_sizes:
            result_normal = pipeline._apply_tier_multiplier(base_size, 'NORMAL', 0.75)
            result_caution = pipeline._apply_tier_multiplier(base_size, 'CAUTION', 0.75)

            ratio = result_caution / result_normal if result_normal != 0 else 0
            expected_ratio = 0.75

            assert ratio == pytest.approx(expected_ratio, rel=0.01), \
                f"Ratio incorrect for base_size={base_size}: got {ratio}, expected {expected_ratio}"
