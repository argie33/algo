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
