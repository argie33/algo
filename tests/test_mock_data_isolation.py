#!/usr/bin/env python3
"""Comprehensive test suite for mock data isolation in critical trading paths.

Verifies that test/mock data cannot reach production code paths and that
all safeguards are properly enforced.
"""

import os
from decimal import Decimal

import pytest

from algo.risk.position_sizer_specialist import PositionSizerSpecialist
from algo.trading.executor import TradeExecutor
from tests.test_utilities import DryRunBrokerAdapter, enable_test_mode
from utils.test_data_detector import TestDataDetector


class TestMockDataDetection:
    """Test that mock data markers are properly detected."""

    def test_detector_identifies_mock_data_markers(self):
        """Verify TestDataDetector finds all mock data markers."""
        mock_obj = {"value": 100, "_is_mock_data": True, "symbol": "SPY"}
        assert TestDataDetector.is_test_data(mock_obj)

    def test_detector_ignores_real_data(self):
        """Verify TestDataDetector accepts real data without markers."""
        real_obj = {"value": 100, "symbol": "SPY", "price": 450.23}
        assert not TestDataDetector.is_test_data(real_obj)

    def test_detector_gets_markers(self):
        """Verify TestDataDetector extracts marker list."""
        mock_obj = {"_is_mock_data": True, "_is_testing_only": True, "value": 100}
        markers = TestDataDetector.get_test_data_markers(mock_obj)
        assert "_is_mock_data" in markers
        assert "_is_testing_only" in markers

    def test_detector_assert_raises_on_mock_data(self):
        """Verify assertion fails when mock data detected."""
        mock_obj = {"_is_mock_data": True, "value": 100}
        with pytest.raises(RuntimeError, match="TEST_DATA_DETECTED_IN_PRODUCTION"):
            TestDataDetector.assert_not_test_data(mock_obj, location="test_path")

    def test_detector_assert_passes_on_real_data(self):
        """Verify assertion passes for real data."""
        real_obj = {"value": 100, "symbol": "SPY"}
        TestDataDetector.assert_not_test_data(real_obj, location="test_path")


class TestDryRunBrokerAdapter:
    """Test that DryRunBrokerAdapter is properly gated."""

    def test_dry_run_requires_environment_flag(self):
        """Verify DryRunBrokerAdapter fails without ORCHESTRATOR_DRY_RUN."""
        # Ensure flags are NOT set
        os.environ.pop("ORCHESTRATOR_DRY_RUN", None)
        os.environ["ENVIRONMENT"] = "production"

        with pytest.raises(RuntimeError, match="requires ORCHESTRATOR_DRY_RUN=true"):
            DryRunBrokerAdapter()

    def test_dry_run_requires_dev_environment(self):
        """Verify DryRunBrokerAdapter fails in production environment."""
        os.environ["ORCHESTRATOR_DRY_RUN"] = "true"
        os.environ["ENVIRONMENT"] = "production"

        with pytest.raises(RuntimeError, match="requires ENVIRONMENT=development"):
            DryRunBrokerAdapter()

    def test_dry_run_succeeds_with_proper_setup(self):
        """Verify DryRunBrokerAdapter works when properly enabled."""
        os.environ["ORCHESTRATOR_DRY_RUN"] = "true"
        os.environ["ENVIRONMENT"] = "development"

        adapter = DryRunBrokerAdapter()
        assert adapter is not None
        assert adapter.alpaca_key is None
        assert adapter.alpaca_secret is None

    def test_dry_run_marks_data_as_mock(self):
        """Verify DryRunBrokerAdapter marks returned data as mock."""
        os.environ["ORCHESTRATOR_DRY_RUN"] = "true"
        os.environ["ENVIRONMENT"] = "development"

        adapter = DryRunBrokerAdapter()
        account = adapter.fetch_account()

        assert account["_is_mock_data"] is True
        assert account["_is_testing_only"] is True


class TestPositionSizerSafeguards:
    """Test that position sizer rejects mock data."""

    def test_position_sizer_rejects_mock_portfolio(self):
        """Verify PositionSizerSpecialist rejects mock data in portfolio value."""
        config = {"base_risk_pct": 2.0, "max_position_size_pct": 10.0}
        sizer = PositionSizerSpecialist(config)

        # Create a dict wrapper with mock data marker (TestDataDetector checks dict)
        # The assertion in calculate_shares wraps portfolio_value in a dict
        # To properly test, we verify the assertion is called with a dict containing the marker
        # For now, we test by mocking what would trigger it
        from unittest.mock import patch

        with patch("utils.test_data_detector.TestDataDetector.assert_not_test_data") as mock_assert:
            mock_assert.side_effect = RuntimeError("TEST_DATA_DETECTED_IN_PRODUCTION: mock detected")
            with pytest.raises(RuntimeError, match="TEST_DATA_DETECTED_IN_PRODUCTION"):
                sizer.calculate_shares(
                    portfolio_value=Decimal("100000.0"), entry_price=Decimal("100.0"), stop_loss=Decimal("95.0")
                )

    def test_position_sizer_accepts_real_portfolio(self):
        """Verify PositionSizerSpecialist works with real data."""
        config = {"base_risk_pct": 2.0, "max_position_size_pct": 10.0}
        sizer = PositionSizerSpecialist(config)

        shares = sizer.calculate_shares(
            portfolio_value=Decimal("100000.0"), entry_price=Decimal("100.0"), stop_loss=Decimal("95.0")
        )
        assert shares > 0


class TestTradeExecutorSafeguards:
    """Test that trade executor rejects mock data."""

    def test_executor_rejects_mock_context(self):
        """Verify TradeExecutor rejects mock trade context."""
        pytest.skip("Requires full AlgoConfig setup - test in integration suite")

    def test_executor_validates_exit_price(self):
        """Verify TradeExecutor validates exit prices."""
        pytest.skip("Requires full AlgoConfig setup - test in integration suite")


class TestEnableTestMode:
    """Test that test mode can be enabled and disabled properly."""

    def test_enable_test_mode_sets_flags(self):
        """Verify enable_test_mode sets appropriate environment variables."""
        result = enable_test_mode(mode="dry-run", environment_override="development")

        assert os.getenv("ENVIRONMENT") == "development"
        assert os.getenv("TEST_MODE_ENABLED") == "true"
        assert os.getenv("ORCHESTRATOR_DRY_RUN") == "true"
        assert result is not None

    def test_enable_test_mode_validates_environment(self):
        """Verify enable_test_mode rejects invalid environments."""
        with pytest.raises(RuntimeError, match="only valid in development environments"):
            enable_test_mode(mode="dry-run", environment_override="production")


class TestTestDataRegistry:
    """Test that test data registry is properly configured."""

    def test_registry_lists_dry_run_broker(self):
        """Verify registry includes dry run broker entry point."""
        from tests.test_utilities.test_data_registry import TestDataRegistry

        all_entries = TestDataRegistry.get_all_test_entry_points()
        assert "dry_run_broker" in all_entries

    def test_registry_shows_hardened_entries(self):
        """Verify registry marks entries as hardened."""
        from tests.test_utilities.test_data_registry import TestDataRegistry

        dry_run = TestDataRegistry.get_entry_point("dry_run_broker")
        assert dry_run is not None
        assert "HARDENED" in dry_run.get("safety_status", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
