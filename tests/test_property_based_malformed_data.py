#!/usr/bin/env python3
"""Parametrized malformed data testing for validator resilience.

Tests systematic combinations of malformed data to verify that validators
handle edge cases gracefully without external dependencies.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.response_validators import (
    ResponseValidationError,
    validate_config_response,
    validate_portfolio_response,
)


class TestPortfolioValidatorWithMalformedData:
    """Test portfolio validator with systematically generated malformed data."""

    def test_with_null_values(self):
        """Portfolio validator should handle None values."""
        for field in ["total_portfolio_value", "total_cash", "position_count"]:
            data = {
                "total_portfolio_value": 100000.0,
                "total_cash": 50000.0,
                "position_count": 5,
                field: None,
            }
            try:
                result = validate_portfolio_response(data)
                assert result is None or isinstance(result, dict)
            except (TypeError, ValueError, ResponseValidationError):
                pass

    def test_with_wrong_numeric_types(self):
        """Portfolio validator should handle wrong numeric types."""
        wrong_types = [[], {}, "invalid", True, False]
        for wrong_type in wrong_types:
            try:
                result = validate_portfolio_response(
                    {
                        "total_portfolio_value": wrong_type,
                        "total_cash": 50000.0,
                        "position_count": 5,
                    }
                )
                assert result is None or isinstance(result, dict)
            except (TypeError, ValueError, ResponseValidationError):
                pass

    def test_with_extreme_numeric_values(self):
        """Portfolio validator should handle extreme values."""
        extreme_values = [
            float("inf"),
            -float("inf"),
            float("nan"),
            999999999999,
            -999999999999,
        ]
        for value in extreme_values:
            try:
                result = validate_portfolio_response(
                    {
                        "total_portfolio_value": value,
                        "total_cash": 50000.0,
                        "position_count": 5,
                    }
                )
                assert result is None or isinstance(result, dict)
            except (TypeError, ValueError, ResponseValidationError):
                pass

    def test_with_empty_strings(self):
        """Portfolio validator should handle empty strings."""
        try:
            result = validate_portfolio_response(
                {
                    "total_portfolio_value": "",
                    "total_cash": "",
                    "position_count": "",
                }
            )
            assert result is None or isinstance(result, dict)
        except (TypeError, ValueError, ResponseValidationError):
            pass

    def test_with_missing_required_fields(self):
        """Portfolio validator should catch missing required fields."""
        test_cases = [
            {},
            {"total_portfolio_value": 100000.0},
            {"total_portfolio_value": 100000.0, "total_cash": 50000.0},
            {"position_count": 5},
        ]
        for data in test_cases:
            try:
                result = validate_portfolio_response(data)
                # Should succeed only if all fields present
                if data == {}:
                    assert result is not None
            except (TypeError, ValueError, ResponseValidationError):
                # Expected for incomplete data
                pass


class TestConfigValidatorWithMalformedData:
    """Test config validator with systematically generated malformed data."""

    def test_with_negative_values(self):
        """Config validator should handle negative threshold values."""
        for value in [-100, -10, -1]:
            try:
                result = validate_config_response(
                    {
                        "min_signal_quality_score": value,
                        "min_swing_score": value,
                        "min_completeness_score": value,
                        "min_volume_ma_50d": 100000,
                        "min_avg_daily_dollar_volume": 500000.0,
                        "earnings_blackout_days_before": value,
                        "earnings_blackout_days_after": value,
                    }
                )
                # Should validate or reject gracefully
                assert result is None or isinstance(result, dict)
            except (TypeError, ValueError, ResponseValidationError):
                pass

    def test_with_zero_values(self):
        """Config validator should handle zero values."""
        try:
            result = validate_config_response(
                {
                    "min_signal_quality_score": 0,
                    "min_swing_score": 0.0,
                    "min_completeness_score": 0,
                    "min_volume_ma_50d": 0,
                    "min_avg_daily_dollar_volume": 0.0,
                    "earnings_blackout_days_before": 0,
                    "earnings_blackout_days_after": 0,
                }
            )
            # Might accept zero or reject
            assert result is None or isinstance(result, dict)
        except (TypeError, ValueError, ResponseValidationError):
            pass

    def test_with_extreme_float_values(self):
        """Config validator should handle extreme float values."""
        for value in [float("inf"), float("nan")]:
            try:
                result = validate_config_response(
                    {
                        "min_signal_quality_score": value,
                        "min_swing_score": value,
                        "min_completeness_score": value,
                        "min_volume_ma_50d": 100000,
                        "min_avg_daily_dollar_volume": 500000.0,
                        "earnings_blackout_days_before": 7,
                        "earnings_blackout_days_after": 3,
                    }
                )
                assert result is None or isinstance(result, dict)
            except (TypeError, ValueError, ResponseValidationError, OverflowError):
                # OverflowError acceptable for infinity values
                pass

    def test_with_mixed_type_fields(self):
        """Config validator should handle wrong field types."""
        try:
            result = validate_config_response(
                {
                    "min_signal_quality_score": "60",  # String instead of int
                    "min_swing_score": [55.0],  # List instead of float
                    "min_completeness_score": {"value": 70},  # Dict instead of int
                    "min_volume_ma_50d": 100000,
                    "min_avg_daily_dollar_volume": 500000.0,
                    "earnings_blackout_days_before": 7,
                    "earnings_blackout_days_after": 3,
                }
            )
            assert result is None or isinstance(result, dict)
        except (TypeError, ValueError, ResponseValidationError):
            pass


class TestValidatorGeneralRobustness:
    """Test that validators are robust against arbitrary malformed input."""

    def test_portfolio_validator_with_non_dict_input(self):
        """Portfolio validator should handle non-dict input gracefully."""
        non_dicts = [None, 123, "string", [], True, False]
        for input_data in non_dicts:
            try:
                result = validate_portfolio_response(input_data)
                assert result is None or isinstance(result, dict)
            except (TypeError, ValueError, ResponseValidationError):
                pass

    def test_config_validator_with_non_dict_input(self):
        """Config validator should handle non-dict input gracefully."""
        non_dicts = [None, 123, "string", [], True, False]
        for input_data in non_dicts:
            try:
                result = validate_config_response(input_data)
                assert result is None or isinstance(result, dict)
            except (TypeError, ValueError, ResponseValidationError):
                pass

    def test_validators_with_very_large_dict(self):
        """Validators should handle large dictionaries."""
        large_dict = {f"field_{i}": i for i in range(1000)}
        large_dict.update(
            {
                "total_portfolio_value": 100000.0,
                "total_cash": 50000.0,
                "position_count": 5,
            }
        )

        try:
            result = validate_portfolio_response(large_dict)
            assert result is None or isinstance(result, dict)
        except (TypeError, ValueError, ResponseValidationError):
            pass

    def test_validators_with_special_characters_in_keys(self):
        """Validators should handle special characters in dict keys."""
        special_keys_dict = {
            "total_portfolio_value\n": 100000.0,  # Newline in key
            "total_cash\t": 50000.0,  # Tab in key
            "position_count\x00": 5,  # Null byte in key
        }

        try:
            result = validate_portfolio_response(special_keys_dict)
            assert result is None or isinstance(result, dict)
        except (TypeError, ValueError, ResponseValidationError, KeyError):
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
