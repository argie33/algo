"""Test response validators for API boundary validation."""

import pytest

from utils.validation.response_validators import (
    ResponseValidationError,
    validate_config_response,
    validate_portfolio_response,
)


class TestConfigResponseValidator:
    """Test config response validation catches missing safety thresholds."""

    def test_valid_config_response(self):
        """Valid config with all critical safety thresholds passes."""
        data = {
            "min_signal_quality_score": 60,
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
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
            "earnings_blackout_days_after": 3,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "min_signal_quality_score" in str(exc_info.value)

    def test_missing_earnings_blackout_days_before(self):
        """Config missing earnings_blackout_days_before raises error."""
        data = {
            "min_signal_quality_score": 60,
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
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
            "earnings_blackout_days_after": 3,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "min_signal_quality_score" in str(exc_info.value)

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
            "min_completeness_score": 70,
            "min_volume_ma_50d": 300000,
            "min_avg_daily_dollar_volume": 500000.0,
            "earnings_blackout_days_before": 7,
            "earnings_blackout_days_after": 3,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_config_response(data)
        assert "Missing critical fields" in str(exc_info.value)


class TestPortfolioResponseValidator:
    """Test portfolio response validation catches missing critical fields."""

    def test_valid_portfolio_response(self):
        """Valid portfolio with all critical fields passes."""
        data = {
            "total_portfolio_value": 100000.0,
            "total_cash": 25000.0,
            "position_count": 5,
            "daily_return_pct": 1.5,
            "unrealized_pnl_pct": 2.3,
            "cumulative_return_pct": 15.4,
            "max_drawdown_pct": -8.2,
            "largest_position_pct": 12.5,
        }
        result = validate_portfolio_response(data)
        assert result == data

    def test_portfolio_error_response_passthrough(self):
        """Portfolio response with _error field passes through without validation."""
        data = {
            "_error": "Database connection failed",
            # Missing required fields but should pass because of _error
        }
        result = validate_portfolio_response(data)
        assert result == data

    def test_portfolio_missing_position_count(self):
        """Portfolio missing position_count raises error."""
        data = {
            "total_portfolio_value": 100000.0,
            "total_cash": 25000.0,
            # Missing position_count
            "daily_return_pct": 1.5,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_portfolio_response(data)
        assert "position_count" in str(exc_info.value)

    def test_portfolio_missing_total_portfolio_value(self):
        """Portfolio missing total_portfolio_value raises error."""
        data = {
            # Missing total_portfolio_value
            "total_cash": 25000.0,
            "position_count": 5,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_portfolio_response(data)
        assert "total_portfolio_value" in str(exc_info.value)

    def test_portfolio_missing_total_cash(self):
        """Portfolio missing total_cash raises error."""
        data = {
            "total_portfolio_value": 100000.0,
            # Missing total_cash
            "position_count": 5,
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_portfolio_response(data)
        assert "total_cash" in str(exc_info.value)

    def test_portfolio_zero_position_count_valid(self):
        """Portfolio with position_count=0 (no open positions) is valid."""
        data = {
            "total_portfolio_value": 100000.0,
            "total_cash": 100000.0,
            "position_count": 0,
            "daily_return_pct": 0.0,
        }
        result = validate_portfolio_response(data)
        assert result["position_count"] == 0

    def test_portfolio_invalid_position_count_type(self):
        """Portfolio with invalid position_count type raises error."""
        data = {
            "total_portfolio_value": 100000.0,
            "total_cash": 25000.0,
            "position_count": "five",  # Should be int
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_portfolio_response(data)
        assert "position_count" in str(exc_info.value)


class TestNewEndpointValidators:
    """Test validators for newly added critical endpoints."""

    def test_last_run_response_valid(self):
        """Valid last-run response passes validation."""
        from utils.validation.response_validators import validate_last_run_response

        data = {
            "run_id": "run_123",
            "success": True,
            "completed_at": "2024-01-15T10:30:00Z",
            "started_at": "2024-01-15T10:20:00Z",
        }
        result = validate_last_run_response(data)
        assert result == data

    def test_last_run_missing_run_id(self):
        """Last-run response missing run_id raises error."""
        from utils.validation.response_validators import validate_last_run_response

        data = {
            "success": True,
            "completed_at": "2024-01-15T10:30:00Z",
        }
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_last_run_response(data)
        assert "run_id" in str(exc_info.value)

    def test_trades_response_valid(self):
        """Valid trades response with items array passes."""
        from utils.validation.response_validators import validate_trades_response

        data = {
            "items": [
                {"symbol": "AAPL", "quantity": 10, "status": "closed"},
                {"symbol": "MSFT", "quantity": 5, "status": "closed"},
            ]
        }
        result = validate_trades_response(data)
        assert result == data

    def test_trades_response_empty_items(self):
        """Trades response with empty items array is valid."""
        from utils.validation.response_validators import validate_trades_response

        data = {"items": []}
        result = validate_trades_response(data)
        assert result == data

    def test_trades_items_not_list(self):
        """Trades response with non-list items raises error."""
        from utils.validation.response_validators import validate_trades_response

        data = {"items": "not_a_list"}
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_trades_response(data)
        assert "items field must be list" in str(exc_info.value)

    def test_markets_response_valid(self):
        """Valid markets response passes validation."""
        from utils.validation.response_validators import validate_markets_response

        data = {
            "current": {"spy_close": 450.25, "exposure_pct": 85.0},
            "market_health": {"vix_level": 18.5, "market_stage": "uptrend"},
        }
        result = validate_markets_response(data)
        assert result == data

    def test_markets_response_empty(self):
        """Markets response that is empty or metadata-only raises error."""
        from utils.validation.response_validators import validate_markets_response

        data = {}
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_markets_response(data)
        assert "empty" in str(exc_info.value)

    def test_dashboard_signals_valid(self):
        """Valid dashboard signals response passes."""
        from utils.validation.response_validators import (
            validate_dashboard_signals_response,
        )

        data = {
            "items": [
                {"symbol": "AAPL", "signal": "buy", "grade": "A"},
                {"symbol": "MSFT", "signal": "hold", "grade": "B"},
            ]
        }
        result = validate_dashboard_signals_response(data)
        assert result == data

    def test_dashboard_signals_no_items(self):
        """Signals response without items key is valid (no signals yet)."""
        from utils.validation.response_validators import (
            validate_dashboard_signals_response,
        )

        data = {"n": 0, "total": 100}
        result = validate_dashboard_signals_response(data)
        assert result == data

    def test_circuit_breakers_valid(self):
        """Valid circuit breakers response passes."""
        from utils.validation.response_validators import (
            validate_circuit_breakers_response,
        )

        data = {
            "breakers": [
                {"name": "max_daily_loss", "triggered": False},
                {"name": "max_position_size", "triggered": True},
            ],
            "any_triggered": True,
        }
        result = validate_circuit_breakers_response(data)
        assert result == data

    def test_circuit_breakers_invalid_type(self):
        """Circuit breakers with non-list breakers raises error."""
        from utils.validation.response_validators import (
            validate_circuit_breakers_response,
        )

        data = {"breakers": "not_a_list"}
        with pytest.raises(ResponseValidationError) as exc_info:
            validate_circuit_breakers_response(data)
        assert "must be list" in str(exc_info.value)

    def test_sector_rotation_valid(self):
        """Valid sector rotation response passes."""
        from dashboard.response_validators import (
            validate_sector_rotation_response,
        )

        data = {
            "items": [
                {"sector": "Technology", "strength": 0.85},
                {"sector": "Healthcare", "strength": 0.72},
            ],
            "signal": "rotate_to_tech",
        }
        result = validate_sector_rotation_response(data)
        assert result == data

    def test_validation_with_error_flag_passes(self):
        """Any response with _error flag passes through without validation."""
        from dashboard.response_validators import (
            validate_last_run_response,
            validate_markets_response,
            validate_trades_response,
        )

        error_data = {"_error": "API call failed"}
        # All validators should pass through error responses
        assert validate_last_run_response(error_data) == error_data
        assert validate_markets_response(error_data) == error_data
        assert validate_trades_response(error_data) == error_data
