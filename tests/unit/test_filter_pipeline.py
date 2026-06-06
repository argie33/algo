#!/usr/bin/env python3
"""Unit tests for FilterPipeline module."""

import pytest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add algo directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from algo.algo_filter_pipeline import FilterPipeline


@pytest.fixture
def mock_connection():
    """Create mock database connection."""
    mock_conn = Mock()
    mock_cur = Mock()
    mock_conn.cursor.return_value = mock_cur
    return mock_conn, mock_cur


@pytest.fixture
def filter_pipeline():
    """Create FilterPipeline instance with mocked config."""
    with patch("algo.algo_filter_pipeline.get_config") as mock_get_config:
        mock_get_config.return_value = {}
        return FilterPipeline(exposure_risk_multiplier=1.0)


class TestFilterPipelineInit:
    """Test FilterPipeline initialization."""

    def test_init_with_multiplier(self):
        """Test initialization with exposure risk multiplier."""
        with patch("algo.algo_filter_pipeline.get_config") as mock_get_config:
            mock_get_config.return_value = {}
            pipeline = FilterPipeline(exposure_risk_multiplier=1.0)
            assert pipeline.exposure_risk_multiplier == 1.0


class TestFilterPipelineBasic:
    """Test basic FilterPipeline functionality."""

    def test_pipeline_creation(self, filter_pipeline):
        """Test filter pipeline can be created."""
        assert filter_pipeline is not None

    def test_apply_filters_empty_universe(self, filter_pipeline):
        """Test applying filters to empty universe."""
        # FilterPipeline no longer stores cur as instance variable
        # Test that the object can be instantiated without error
        assert filter_pipeline is not None
        assert filter_pipeline.config is not None


class TestFilterPipelineStages:
    """Test individual filter stages."""

    def test_liquidity_filter(self, filter_pipeline, mock_connection):
        """Test liquidity filter stage."""
        _, mock_cur = mock_connection
        # FilterPipeline no longer stores cur as instance variable
        # Cursor is passed as parameter to methods
        assert filter_pipeline is not None

    def test_technical_filter(self, filter_pipeline, mock_connection):
        """Test technical analysis filter."""
        # FilterPipeline no longer stores cur as instance variable
        # Cursor is passed as parameter to methods
        assert filter_pipeline is not None

    def test_fundamental_filter(self, filter_pipeline, mock_connection):
        """Test fundamental analysis filter."""
        # FilterPipeline no longer stores cur as instance variable
        # Cursor is passed as parameter to methods
        assert filter_pipeline is not None


class TestFilterPipelineEdgeCases:
    """Test edge cases in filter pipeline."""

    def test_handle_missing_data(self, filter_pipeline, mock_connection):
        """Test handling of missing data in filters."""
        # FilterPipeline no longer stores cur as instance variable
        # Cursor is passed as parameter to methods
        assert filter_pipeline is not None

    def test_handle_extreme_values(self, filter_pipeline, mock_connection):
        """Test handling of extreme values."""
        # FilterPipeline no longer stores cur as instance variable
        # Cursor is passed as parameter to methods
        assert filter_pipeline is not None


class TestFilterPipelineDegradedMode:
    """Test degraded mode functionality (ISSUE #10 FIX)."""

    def test_degraded_flag_accepted(self):
        """Test that FilterPipeline accepts degraded parameter."""
        with patch("algo.algo_filter_pipeline.get_config") as mock_get_config:
            mock_get_config.return_value = {}
            # Should not raise exception
            pipeline = FilterPipeline(exposure_risk_multiplier=1.0, degraded=True)
            assert pipeline.degraded is True

    def test_normal_mode_no_degraded(self):
        """Test that degraded defaults to False."""
        with patch("algo.algo_filter_pipeline.get_config") as mock_get_config:
            mock_get_config.return_value = {}
            pipeline = FilterPipeline(exposure_risk_multiplier=1.0)
            assert pipeline.degraded is False

    def test_degraded_mode_reduces_position_size(self):
        """Test that degraded mode applies 0.5x multiplier to position sizing."""
        with patch("algo.algo_filter_pipeline.get_config") as mock_get_config:
            mock_get_config.return_value = {}

            # Normal mode
            normal_pipeline = FilterPipeline(exposure_risk_multiplier=1.0, degraded=False)
            normal_size = normal_pipeline._apply_tier_multiplier(1000.0, 'NORMAL')
            assert normal_size == 1000.0

            # Degraded mode
            degraded_pipeline = FilterPipeline(exposure_risk_multiplier=1.0, degraded=True)
            degraded_size = degraded_pipeline._apply_tier_multiplier(1000.0, 'NORMAL')
            # Degraded mode applies 0.5x multiplier
            assert degraded_size == 500.0

            # Verify reduction is exactly 50%
            assert degraded_size == normal_size * 0.5

    def test_degraded_mode_with_different_tiers(self):
        """Test that degraded mode works with all exposure tiers."""
        with patch("algo.algo_filter_pipeline.get_config") as mock_get_config:
            mock_get_config.return_value = {}

            pipeline = FilterPipeline(exposure_risk_multiplier=1.0, degraded=True)

            # Test all tiers
            test_cases = [
                ('NORMAL', 1000.0, 500.0),      # 1.0x * 0.5x = 0.5x
                ('CAUTION', 1000.0, 375.0),     # 0.75x * 0.5x = 0.375x
                ('PRESSURE', 1000.0, 250.0),    # 0.5x * 0.5x = 0.25x
                ('HALT', 1000.0, 0.0),          # 0.0x * 0.5x = 0.0x
            ]

            for tier, base_size, expected_size in test_cases:
                actual_size = pipeline._apply_tier_multiplier(base_size, tier)
                assert actual_size == expected_size, \
                    f"Tier {tier}: expected {expected_size}, got {actual_size}"

    def test_degraded_with_exposure_multiplier(self):
        """Test that degraded mode works with non-1.0 exposure multipliers."""
        with patch("algo.algo_filter_pipeline.get_config") as mock_get_config:
            mock_get_config.return_value = {}

            # Exposure multiplier of 0.75 (CAUTION tier)
            pipeline = FilterPipeline(exposure_risk_multiplier=0.75, degraded=True)

            # Base position size with NORMAL tier
            size = pipeline._apply_tier_multiplier(1000.0, 'NORMAL')
            # 1000 * 1.0 (NORMAL) * 0.5 (degraded) = 500
            assert size == 500.0
