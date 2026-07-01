"""Integration tests for fetcher StrictValidationError handling.

Tests that fetchers properly handle and report StrictValidationError when
strict=True conversions fail on None or invalid data from API responses.
"""

from unittest.mock import patch

import pytest

from dashboard.fetchers_external import fetch_economic_pulse
from dashboard.fetchers_portfolio import fetch_perf_analytics
from dashboard.fetchers_signals import fetch_signal_eval
from utils.safe_data_conversion import StrictValidationError


class TestFetchEconomicPulseStrictValidation:
    """Test fetch_economic_pulse handles None values in critical fields."""

    def test_fetch_economic_pulse_missing_yield_10y_raises(self) -> None:
        """fetch_economic_pulse must catch StrictValidationError when 10Y yield is None."""
        incomplete_response = {
            "currentCurve": {
                "10Y": None,  # CRITICAL: Missing 10Y yield
                "2Y": 4.5,
                "3M": 5.2,
                "6M": 5.1,
            },
            "spreads": {
                "T10Y2Y": 0.5,
                "T10Y3M": -0.1,
            },
            "credit": {
                "currentSpreads": {
                    "BAMLH0A0HYM2": 350.0,
                    "BAMLH0A0IG": 150.0,
                }
            },
        }

        with patch("dashboard.fetchers_external.api_call") as mock_api:
            # First call returns yield curve with missing 10Y, second call returns indicators
            mock_api.side_effect = [
                incomplete_response,
                {  # indicators response
                    "currentValues": {"CPI": 3.2, "UnemploymentRate": 3.8},
                },
            ]

            result = fetch_economic_pulse(None)

            # Should return error response, not raise StrictValidationError
            assert "_error" in result, f"Expected error response, got: {result}"
            assert "10Y" in result.get("_error", "").lower() or "cannot convert" in result.get("_error", "").lower()

    def test_fetch_economic_pulse_missing_spread_raises(self) -> None:
        """fetch_economic_pulse must catch StrictValidationError when spreads are None."""
        incomplete_response = {
            "currentCurve": {
                "10Y": 4.0,
                "2Y": 4.5,
                "3M": 5.2,
                "6M": 5.1,
            },
            "spreads": {
                "T10Y2Y": None,  # CRITICAL: Missing spread
                "T10Y3M": -0.1,
            },
            "credit": {
                "currentSpreads": {
                    "BAMLH0A0HYM2": 350.0,
                    "BAMLH0A0IG": 150.0,
                }
            },
        }

        with patch("dashboard.fetchers_external.api_call") as mock_api:
            mock_api.side_effect = [
                incomplete_response,
                {
                    "currentValues": {"CPI": 3.2, "UnemploymentRate": 3.8},
                },
            ]

            result = fetch_economic_pulse(None)

            assert "_error" in result, f"Expected error response, got: {result}"

    def test_fetch_economic_pulse_with_invalid_spread_type_raises(self) -> None:
        """fetch_economic_pulse must catch StrictValidationError when spread is non-numeric string."""
        incomplete_response = {
            "currentCurve": {
                "10Y": 4.0,
                "2Y": 4.5,
                "3M": 5.2,
                "6M": 5.1,
            },
            "spreads": {
                "T10Y2Y": "invalid_number",  # CRITICAL: Invalid type
                "T10Y3M": -0.1,
            },
            "credit": {
                "currentSpreads": {
                    "BAMLH0A0HYM2": 350.0,
                    "BAMLH0A0IG": 150.0,
                }
            },
        }

        with patch("dashboard.fetchers_external.api_call") as mock_api:
            mock_api.side_effect = [
                incomplete_response,
                {
                    "indicators": [
                        {"series_id": "FEDFUNDS", "rawValue": 5.33},
                    ]
                },
            ]

            result = fetch_economic_pulse(None)

            # Should return error response, not raise StrictValidationError
            assert "_error" in result, f"Expected error response, got: {result}"


class TestFetchPerfAnalyticsStrictValidation:
    """Test fetch_perf_analytics handles None values in critical fields."""

    def test_fetch_perf_analytics_missing_sharpe_raises(self) -> None:
        """fetch_perf_analytics must catch StrictValidationError when sharpe is None."""
        incomplete_data = {
            "rolling_sharpe_252d": None,  # CRITICAL: Missing sharpe
            "rolling_sortino_252d": 2.5,
            "calmar_ratio": 1.5,
            "win_rate_50t": 55,
            "avg_win_r_50t": 1.2,
            "avg_loss_r_50t": -0.8,
            "expectancy": 0.5,
            "max_drawdown_pct": -15.0,
        }

        with patch("dashboard.fetchers_portfolio.api_call", return_value=incomplete_data):
            result = fetch_perf_analytics(None)

            # Should return error response, not raise StrictValidationError
            assert "_error" in result, f"Expected error response, got: {result}"

    def test_fetch_perf_analytics_all_valid_succeeds(self) -> None:
        """fetch_perf_analytics succeeds when all fields are present and valid."""
        complete_data = {
            "rolling_sharpe_252d": 1.8,
            "rolling_sortino_252d": 2.5,
            "calmar_ratio": 1.5,
            "win_rate_50t": 55,
            "avg_win_r_50t": 1.2,
            "avg_loss_r_50t": -0.8,
            "expectancy": 0.5,
            "max_drawdown_pct": -15.0,
        }

        with patch("dashboard.fetchers_portfolio.api_call", return_value=complete_data):
            result = fetch_perf_analytics(None)

            assert "_error" not in result
            assert result.get("sharpe252") == 1.8


class TestFetchSignalEvalStrictValidation:
    """Test fetch_signal_eval handles None values properly with strict mode."""

    def test_fetch_signal_eval_none_total_returns_none(self) -> None:
        """fetch_signal_eval with None total should return None, not raise."""
        response = {
            "total": None,  # None is acceptable for optional fields
            "t1": None,
            "t2": None,
            "t3": None,
            "t4": None,
            "t5": None,
            "avg_score": None,
            "signal_date": None,
            "rejected": None,
        }

        with patch("dashboard.fetchers_signals.api_call", return_value=response):
            result = fetch_signal_eval(None)

            # Should succeed and return None values, not error
            assert "_error" not in result
            assert result.get("total") is None

    def test_fetch_signal_eval_invalid_int_raises(self) -> None:
        """fetch_signal_eval with invalid int should catch error."""
        response = {
            "total": "not_an_int",  # Invalid type
            "t1": 5,
            "t2": None,
            "t3": None,
            "t4": None,
            "t5": None,
            "avg_score": None,
            "signal_date": None,
            "rejected": None,
        }

        with patch("dashboard.fetchers_signals.api_call", return_value=response):
            result = fetch_signal_eval(None)

            # Should return error response
            assert "_error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
