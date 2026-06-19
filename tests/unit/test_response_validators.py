"""Test response validators for API boundary validation."""

import pytest

from tools.dashboard.response_validators import (
    ResponseValidationError,
    validate_config_response,
)


class TestConfigResponseValidator:
    """Test config response validation catches missing safety thresholds."""

    def test_valid_config_response(self):
        """Valid config with all critical safety thresholds passes."""
        data = {
            "min_signal_quality_score": 60,
            "min_swing_score": 55.0,
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
            "earnings_blackout_days_after": 3,
        }
        result = validate_config_response(data)
        assert result == data

    def test_error_response_passthrough(self):
        """Config response with _error field passes through without validation."""
        data = {
            "_error": "Database connection failed",
            # Missing required fields but should pass because of _error
        }
        result = validate_config_response(data)
        assert result == data

    def test_missing_min_signal_quality_score(self):
        """Config missing min_signal_quality_score raises error."""
        data = {
            "min_swing_score": 55.0,
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
            "earnings_blackout_days_after": 3,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "min_signal_quality_score" in str(exc_info.value)

    def test_missing_min_swing_score(self):
        """Config missing min_swing_score raises error."""
        data = {
            "min_signal_quality_score": 60,
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
            "earnings_blackout_days_after": 3,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "min_swing_score" in str(exc_info.value)

    def test_missing_earnings_blackout_days_before(self):
        """Config missing earnings_blackout_days_before raises error."""
        data = {
            "min_signal_quality_score": 60,
            "min_swing_score": 55.0,
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_after": 3,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "earnings_blackout_days_before" in str(exc_info.value)

    def test_missing_earnings_blackout_days_after(self):
        """Config missing earnings_blackout_days_after raises error."""
        data = {
            "min_signal_quality_score": 60,
            "min_swing_score": 55.0,
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "earnings_blackout_days_after" in str(exc_info.value)

    def test_invalid_min_signal_quality_score_type(self):
        """Config with invalid min_signal_quality_score type raises error."""
        data = {
            "min_signal_quality_score": "not_a_number",  # Should be int
            "min_swing_score": 55.0,
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
            "earnings_blackout_days_after": 3,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "min_signal_quality_score" in str(exc_info.value)

    def test_invalid_min_swing_score_type(self):
        """Config with invalid min_swing_score type raises error."""
        data = {
            "min_signal_quality_score": 60,
            "min_swing_score": "not_a_number",  # Should be float
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
            "earnings_blackout_days_after": 3,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "min_swing_score" in str(exc_info.value)

    def test_empty_config_dict(self):
        """Empty config dict raises error (must have all required fields)."""
        data = {}
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "Missing critical fields" in str(exc_info.value)

    def test_config_not_dict(self):
        """Non-dict config response raises error."""
        data = []  # type: ignore
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "not a dict" in str(exc_info.value)

    def test_null_critical_field(self):
        """Config with None value for critical field raises error."""
        data = {
            "min_signal_quality_score": None,  # Should not be None
            "min_swing_score": 55.0,
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
            "earnings_blackout_days_after": 3,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "Missing critical fields" in str(exc_info.value)
