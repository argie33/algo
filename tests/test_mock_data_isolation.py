#!/usr/bin/env python3
"""Comprehensive test suite for mock data isolation in critical trading paths.

Verifies that test/mock data cannot reach production code paths and that
all safeguards are properly enforced.

FIXED 2026-08-23 (goal: pre-real-money accuracy review): this file's own docstring claim
was false for two of its test classes. `TestMockDataDetection` and (the former)
`TestPositionSizerSafeguards` exercised `utils/test_data_detector.py::TestDataDetector` and
`algo/risk/position_sizer_specialist.py::PositionSizerSpecialist` - neither was imported by
any live production code path (`phase8_entry_execution.py` has always used
`algo/trading/position_sizer.py::PositionSizer` instead; grep-confirmed
`position_sizer_specialist` had exactly one non-test consumer - itself). The marker-dict
scanner they tested was dead code from an old "Feature Envy fix" refactor extraction that
never got wired in, so this suite was giving false assurance that mock data couldn't reach
production position sizing, while the actual production class had no such check at all.
Deleted both dead files and replaced the coverage with a real regression test below
(`TestPositionSizerSafeguards.test_position_sizer_rejects_dict_shaped_portfolio_value`)
against the live `PositionSizer` class - it turns out already protected against this exact
scenario, just via a different, more general mechanism (fail-fast Decimal conversion, not a
marker scan): a mock-marked dict passed as `portfolio_value` fails `Decimal(str(x))` with
`InvalidOperation` before any sizing math runs, converted to `ValueError` by
`_calculate_with_external_cursor`'s existing conversion guard. `TestDryRunBrokerAdapter`/
`TestEnableTestMode`/`TestTestDataRegistry` below were unaffected - all three test real,
live-wired safeguards (`ENVIRONMENT`/`ORCHESTRATOR_DRY_RUN` env-var gating), not orphaned code.
"""

import os
from decimal import Decimal

import pytest

from algo.trading.executor import TradeExecutor
from algo.trading.position_sizer import PositionSizer
from tests.test_utilities import DryRunBrokerAdapter, enable_test_mode


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
    """Test that the LIVE position sizer (algo/trading/position_sizer.py - the class
    phase8_entry_execution.py actually imports) rejects mock-shaped data, not the orphaned
    PositionSizerSpecialist this class used to test (deleted 2026-08-23 - see module
    docstring)."""

    _CONFIG = {
        "base_risk_pct": 0.75,
        "max_positions": 12,
        "risk_reduction_at_minus_5": 0.75,
        "risk_reduction_at_minus_10": 0.5,
        "risk_reduction_at_minus_15": 0.25,
        "risk_reduction_at_minus_20": 0,
        "vix_caution_threshold": 25,
        "vix_max_threshold": 35,
        "vix_caution_risk_reduction": 0.5,
        "max_position_size_pct": 8,
        "max_concentration_pct": 20,
        "max_total_invested_pct": 80,
        "max_total_risk_pct": 8,
        "min_risk_pct_floor": 0.25,
    }

    def test_position_sizer_rejects_dict_shaped_portfolio_value(self):
        """A mock-marked dict passed as portfolio_value (e.g. an accidentally-unwrapped test
        fixture) must never silently flow into position-sizing math. The live PositionSizer
        has no marker-scanning check, but its portfolio_value normalization
        (`Decimal(str(portfolio_value))`, applied before any other calculation) already fails
        closed on anything that isn't a real number - a dict's str() representation is never
        a valid Decimal literal. This runs with zero DB access: the conversion happens before
        any cursor use."""
        sizer = PositionSizer(self._CONFIG)
        mock_portfolio = {"_is_mock_data": True, "_is_testing_only": True, "portfolio_value": 100000}

        with pytest.raises(RuntimeError, match="Position sizing calculation failed"):
            sizer.calculate_position_size(
                symbol="AAPL",
                entry_price=Decimal("100.0"),
                stop_loss_price=Decimal("95.0"),
                portfolio_value=mock_portfolio,
            )


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
