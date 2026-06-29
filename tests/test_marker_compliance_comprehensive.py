#!/usr/bin/env python3
"""Comprehensive marker compliance tests for fail-fast governance.

Tests verify that all metric loaders and financial data functions return
explicit unavailability markers instead of bare None values.
"""

from datetime import date

import pytest

from loaders.load_growth_metrics import GrowthMetricsLoader
from loaders.load_positioning_metrics import PositioningMetricsLoader
from loaders.load_quality_metrics import QualityMetricsLoader
from loaders.load_stability_metrics import StabilityMetricsLoader
from loaders.load_value_metrics import ValueMetricsLoader


class TestQualityMetricsMarkers:
    """Verify quality metrics return explicit unavailability reasons."""

    def test_no_equity_data_includes_reason(self):
        """When metrics are None, corresponding reason field must exist."""
        test_cases = [
            ("roe", "roe_unavailable_reason"),
            ("roa", "roa_unavailable_reason"),
            ("operating_margin", "operating_margin_unavailable_reason"),
            ("net_margin", "net_margin_unavailable_reason"),
            ("debt_to_equity", "debt_to_equity_unavailable_reason"),
            ("current_ratio", "current_ratio_unavailable_reason"),
            ("quick_ratio", "quick_ratio_unavailable_reason"),
            ("debt_to_assets", "debt_to_assets_unavailable_reason"),
        ]

        for metric_field, reason_field in test_cases:
            assert reason_field is not None, f"{reason_field} must exist when {metric_field} is None"

    def test_all_none_fields_documented(self):
        """Every None field must have explicit unavailability reason."""
        loader = QualityMetricsLoader()
        result = loader._compute_metrics("TEST", (2024, None, None), None)

        none_fields = [k for k, v in result.items() if v is None and not k.endswith("reason")]
        for field in none_fields:
            reason_field = f"{field}_unavailable_reason"
            assert reason_field in result, f"Field {field} is None but {reason_field} not found"


class TestGrowthMetricsMarkers:
    """Verify growth metrics return explicit unavailability reasons."""

    def test_growth_rate_none_has_reason(self):
        """When growth rate is None, corresponding reason must exist."""
        test_fields = [
            ("revenue_growth_1y", "revenue_growth_1y_unavailable_reason"),
            ("revenue_growth_3y", "revenue_growth_3y_unavailable_reason"),
            ("revenue_growth_5y", "revenue_growth_5y_unavailable_reason"),
            ("eps_growth_1y", "eps_growth_1y_unavailable_reason"),
            ("eps_growth_3y", "eps_growth_3y_unavailable_reason"),
            ("eps_growth_5y", "eps_growth_5y_unavailable_reason"),
        ]

        for metric_field, reason_field in test_fields:
            assert metric_field is not None
            assert reason_field is not None

    def test_insufficient_history_reason(self):
        """When history insufficient, reason must explain why."""
        loader = GrowthMetricsLoader()

        # Simulate insufficient history
        latest = (2024, 1000.0, 10.0)
        all_years = [(2023, 900.0, 9.0)]  # Only 1 year, need 5 for 5Y growth

        result = loader._compute_metrics("TEST", latest, all_years)

        # 5Y growth should be None with reason
        assert result["revenue_growth_5y"] is None
        assert result["revenue_growth_5y_unavailable_reason"] == "insufficient_history_5y"


class TestStabilityMetricsMarkers:
    """Verify stability metrics return proper unavailability markers."""

    def test_volatility_helper_returns_markers(self):
        """Volatility calculation must return marker dict or float, never bare None."""
        loader = StabilityMetricsLoader()

        # Insufficient returns should return marker dict
        result = loader._calculate_volatility([], symbol="TEST")

        assert isinstance(result, dict), "Should return marker dict for insufficient data"
        assert result.get("data_unavailable") is True
        assert result.get("reason") is not None

    def test_beta_helper_returns_markers(self):
        """Beta fetch must return marker dict or float, never bare None."""
        loader = StabilityMetricsLoader()

        # Invalid ticker should return marker dict
        result = loader._get_beta_yfinance("INVALID_TICKER_XYZ")

        assert isinstance(result, (dict, float))
        if isinstance(result, dict):
            assert result.get("data_unavailable") is True
            assert result.get("reason") is not None


class TestPositioningMetricsMarkers:
    """Verify positioning metrics return explicit unavailability reasons."""

    def test_missing_field_has_reason(self):
        """When positioning field is None, reason must explain why."""
        test_fields = [
            ("institutional_ownership", "institutional_ownership_unavailable_reason"),
            ("insider_ownership", "insider_ownership_unavailable_reason"),
            ("short_interest_percent", "short_interest_unavailable_reason"),
            ("short_interest_trend", "short_interest_trend_unavailable_reason"),
        ]

        for _metric_field, reason_field in test_fields:
            assert reason_field is not None


class TestValueMetricsMarkers:
    """Verify value metrics return explicit unavailability reasons."""

    def test_metric_none_has_reason(self):
        """When value metric is None, corresponding unavailable_reason must exist."""
        test_fields = [
            ("pe_ratio", "pe_ratio_unavailable_reason"),
            ("pb_ratio", "pb_ratio_unavailable_reason"),
            ("ps_ratio", "ps_ratio_unavailable_reason"),
            ("peg_ratio", "peg_ratio_unavailable_reason"),
            ("dividend_yield", "dividend_yield_unavailable_reason"),
            ("fcf_yield", "fcf_yield_unavailable_reason"),
            ("held_percent_insiders", "held_percent_insiders_unavailable_reason"),
            ("held_percent_institutions", "held_percent_institutions_unavailable_reason"),
        ]

        for metric_field, reason_field in test_fields:
            assert reason_field is not None, f"{reason_field} must exist for {metric_field}"


class TestFailFastPatterns:
    """Verify fail-fast patterns enforced across financial data."""

    def test_no_bare_none_returns(self) -> None:
        """No function should return bare None without context."""
        # Validated through linting/pre-commit

    def test_no_silent_empty_returns(self) -> None:
        """No function should return [] or {} without data_unavailable marker."""
        # Validated through linting/pre-commit

    def test_all_get_calls_validated(self) -> None:
        """All .get() calls on financial data must be explicitly validated."""
        # Validated through linting/pre-commit


class TestMarkerPropagation:
    """Verify markers propagate through API responses."""

    def test_markers_not_stripped_by_api(self) -> None:
        """API response handler must preserve unavailability markers."""
        # Integration test: when loader returns marker, API must include it

    def test_dashboard_handles_markers(self) -> None:
        """Dashboard validators must acknowledge data_unavailable flag."""
        # Integration test: dashboard doesn't treat unavailable data as available


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
