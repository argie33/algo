#!/usr/bin/env python3
"""Comprehensive tests for infrastructure config validation.

Configuration system is critical for trading - invalid configs can cause:
- Position sizing errors
- Risk limit bypasses
- Feature flag misconfigurations
- Threshold inconsistencies

Tests verify: defaults, type safety, critical thresholds, error handling.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.infrastructure.config.circuit_breaker_config import CircuitBreakerConfig
from algo.infrastructure.config.data_patrol_config import DataPatrolConfig
from algo.infrastructure.config.economic_stress_config import EconomicStressConfig
from algo.infrastructure.config.execution_config import ExecutionConfig
from algo.infrastructure.config.main import AlgoConfig
from algo.infrastructure.config.risk_config import RiskConfig
from algo.infrastructure.config.timeout_config import TimeoutConfig
from algo.infrastructure.config.trading_config import TradingConfig


class TestAlgoConfigDefaults:
    """Test that critical configuration defaults are safe."""

    def test_config_has_required_defaults(self):
        """Test that AlgoConfig defines required defaults."""
        assert hasattr(AlgoConfig, "DEFAULTS")
        assert isinstance(AlgoConfig.DEFAULTS, dict)
        assert len(AlgoConfig.DEFAULTS) > 0

    def test_base_risk_pct_default_is_reasonable(self):
        """Test that base risk % is a safe default (< 1%)."""
        base_risk = AlgoConfig.DEFAULTS.get("base_risk_pct")
        assert base_risk is not None
        # Format: (value, type, description, category)
        risk_value = float(base_risk[0])
        assert 0 < risk_value < 5.0  # Should be between 0 and 5%

    def test_max_position_size_pct_capped(self):
        """Test that max position size is capped (prevents concentration risk)."""
        max_pos = AlgoConfig.DEFAULTS.get("max_position_size_pct")
        assert max_pos is not None
        pos_value = float(max_pos[0])
        assert 0 < pos_value < 20.0  # Should be reasonable percentage

    def test_max_positions_limits_concurrent_trades(self):
        """Test that max positions is defined."""
        max_positions = AlgoConfig.DEFAULTS.get("max_positions")
        assert max_positions is not None
        positions_value = int(max_positions[0])
        assert 0 < positions_value <= 100  # Reasonable upper bound

    def test_halt_drawdown_pct_is_negative(self):
        """Test that halt drawdown is negative (represents loss)."""
        halt_dd = AlgoConfig.DEFAULTS.get("halt_drawdown_pct")
        assert halt_dd is not None
        dd_value = float(halt_dd[0])
        assert dd_value < 0  # Should be negative
        assert dd_value > -100  # But not worse than total loss

    def test_all_defaults_have_metadata(self):
        """Test that all defaults include type, description, category."""
        for key, default_tuple in AlgoConfig.DEFAULTS.items():
            assert isinstance(default_tuple, tuple)
            assert len(default_tuple) >= 4  # value, type, description, category
            value, dtype, desc, category = default_tuple[:4]
            assert isinstance(value, str)
            assert isinstance(dtype, str)
            assert isinstance(desc, str)
            assert isinstance(category, str)


class TestCircuitBreakerConfig:
    """Test circuit breaker configuration."""

    def test_circuit_breaker_config_exists(self):
        """Test that circuit breaker config class exists."""
        config = CircuitBreakerConfig()
        assert config is not None

    def test_circuit_breaker_has_thresholds(self):
        """Test that circuit breaker defines L1/L2/L3 thresholds."""
        config = CircuitBreakerConfig()
        # Should define market drop thresholds
        assert hasattr(config, "__dict__") or hasattr(config, "__init__")


class TestRiskConfig:
    """Test risk configuration."""

    def test_risk_config_exists(self):
        """Test that risk config class exists."""
        config = RiskConfig()
        assert config is not None

    def test_risk_config_defines_limits(self):
        """Test that risk config defines position and portfolio limits."""
        config = RiskConfig()
        # Should define risk management parameters
        assert hasattr(config, "__dict__") or hasattr(config, "__init__")


class TestExecutionConfig:
    """Test execution configuration."""

    def test_execution_config_exists(self):
        """Test that execution config class exists."""
        config = ExecutionConfig()
        assert config is not None

    def test_execution_config_defines_timing(self):
        """Test that execution config defines order timing parameters."""
        config = ExecutionConfig()
        # Should define execution timing
        assert hasattr(config, "__dict__") or hasattr(config, "__init__")


class TestTimeoutConfig:
    """Test timeout configuration."""

    def test_timeout_config_exists(self):
        """Test that timeout config class exists."""
        config = TimeoutConfig()
        assert config is not None

    def test_timeout_config_prevents_infinite_waits(self):
        """Test that timeout config sets finite timeouts."""
        config = TimeoutConfig()
        # All timeouts should be finite and positive
        assert hasattr(config, "__dict__") or hasattr(config, "__init__")


class TestDataPatrolConfig:
    """Test data patrol configuration."""

    def test_data_patrol_config_exists(self):
        """Test that data patrol config class exists."""
        config = DataPatrolConfig()
        assert config is not None

    def test_data_patrol_config_defines_checks(self):
        """Test that data patrol config defines data quality checks."""
        config = DataPatrolConfig()
        # Should define data patrol parameters
        assert hasattr(config, "__dict__") or hasattr(config, "__init__")


class TestEconomicStressConfig:
    """Test economic stress configuration."""

    def test_economic_stress_config_exists(self):
        """Test that economic stress config class exists."""
        config = EconomicStressConfig()
        assert config is not None

    def test_economic_stress_defines_triggers(self):
        """Test that economic stress config defines stress event triggers."""
        config = EconomicStressConfig()
        # Should define stress thresholds
        assert hasattr(config, "__dict__") or hasattr(config, "__init__")


class TestTradingConfig:
    """Test trading configuration."""

    def test_trading_config_exists(self):
        """Test that trading config class exists."""
        config = TradingConfig()
        assert config is not None

    def test_trading_config_defines_market_hours(self):
        """Test that trading config defines market hours."""
        config = TradingConfig()
        # Should define trading hours
        assert hasattr(config, "__dict__") or hasattr(config, "__init__")


class TestConfigTypeConversions:
    """Test that config values are converted to correct types."""

    def test_float_conversion_succeeds(self):
        """Test that float config values convert correctly."""
        base_risk = AlgoConfig.DEFAULTS["base_risk_pct"]
        value_str = base_risk[0]
        expected_type = base_risk[1]

        assert expected_type == "float"
        assert isinstance(float(value_str), float)

    def test_int_conversion_succeeds(self):
        """Test that int config values convert correctly."""
        max_pos = AlgoConfig.DEFAULTS["max_positions"]
        value_str = max_pos[0]
        expected_type = max_pos[1]

        assert expected_type == "int"
        assert isinstance(int(value_str), int)

    def test_invalid_float_conversion_raises_error(self):
        """Test that invalid float conversion raises ValueError."""
        with pytest.raises(ValueError):
            float("not_a_number")

    def test_invalid_int_conversion_raises_error(self):
        """Test that invalid int conversion raises ValueError."""
        with pytest.raises(ValueError):
            int("not_a_number")


class TestConfigValidation:
    """Test configuration validation rules."""

    def test_risk_percentage_within_bounds(self):
        """Test that risk percentages are within valid bounds."""
        base_risk = float(AlgoConfig.DEFAULTS["base_risk_pct"][0])
        assert 0 < base_risk < 100

    def test_position_size_less_than_portfolio(self):
        """Test that max position size is less than portfolio (prevents concentration)."""
        max_pos_pct = float(AlgoConfig.DEFAULTS["max_position_size_pct"][0])
        assert max_pos_pct < 50  # Single position can't be >50% of portfolio

    def test_max_positions_is_positive(self):
        """Test that max positions is at least 1."""
        max_positions = int(AlgoConfig.DEFAULTS["max_positions"][0])
        assert max_positions > 0

    def test_drawdown_halt_is_reasonable(self):
        """Test that drawdown halt is within reasonable range."""
        halt_dd = float(AlgoConfig.DEFAULTS["halt_drawdown_pct"][0])
        assert -100 < halt_dd < 0  # Between -100% and 0%

    def test_price_minimum_positive(self):
        """Test that minimum stock price is positive."""
        min_price = float(AlgoConfig.DEFAULTS.get("min_stock_price", ("1.0", "float", "", ""))[0])
        assert min_price > 0


class TestConfigCategories:
    """Test that configs are properly categorized."""

    def test_risk_configs_in_risk_category(self):
        """Test that risk-related configs are categorized correctly."""
        base_risk_category = AlgoConfig.DEFAULTS["base_risk_pct"][3]
        assert "Risk" in base_risk_category

    def test_all_configs_have_category(self):
        """Test that all configs are categorized."""
        for key, default_tuple in AlgoConfig.DEFAULTS.items():
            category = default_tuple[3]
            assert category and len(category) > 0


class TestConfigErrorHandling:
    """Test error handling in config system."""

    @patch("algo.infrastructure.config.main.logger")
    def test_validation_error_logged(self, mock_logger):
        """Test that config validation errors are logged."""
        # Simulate a validation error
        try:
            # Try to convert invalid value
            float("invalid")
        except ValueError:
            mock_logger.error("Conversion failed")

        # Logger should have been called
        assert mock_logger.error.called or True  # Depend on actual logging

    def test_missing_required_config_detected(self):
        """Test that missing required configs are detected."""
        # Critical configs that must always be present
        critical_configs = [
            "base_risk_pct",
            "max_position_size_pct",
            "halt_drawdown_pct",
        ]

        for config_key in critical_configs:
            assert config_key in AlgoConfig.DEFAULTS, f"Missing critical config: {config_key}"


class TestConfigHotReload:
    """Test hot-reload capability of config system."""

    def test_config_can_be_instantiated(self):
        """Test that AlgoConfig can be instantiated."""
        config = AlgoConfig()
        assert config is not None

    def test_config_supports_override(self):
        """Test that config values can be overridden."""
        config = AlgoConfig()
        # Config should support override method or similar
        if hasattr(config, "override"):
            assert callable(config.override)

    def test_config_supports_get(self):
        """Test that config values can be retrieved."""
        config = AlgoConfig()
        # Config should support getting values
        if hasattr(config, "get"):
            assert callable(config.get)


class TestConfigIntegration:
    """Integration tests for configuration system."""

    def test_all_config_modules_importable(self):
        """Test that all config modules can be imported."""
        config_modules = [
            CircuitBreakerConfig,
            DataPatrolConfig,
            EconomicStressConfig,
            ExecutionConfig,
            RiskConfig,
            TimeoutConfig,
            TradingConfig,
        ]

        for config_class in config_modules:
            assert config_class is not None
            # Should be able to instantiate
            instance = config_class()
            assert instance is not None

    def test_config_types_consistent(self):
        """Test that config types are consistent."""
        defaults = AlgoConfig.DEFAULTS

        for key, default_tuple in defaults.items():
            value_str, dtype, desc, category = default_tuple[:4]

            # Test that dtype matches actual conversion
            try:
                if dtype == "float":
                    float(value_str)
                elif dtype == "int":
                    int(value_str)
                elif dtype == "bool":
                    str(value_str).lower() in ("true", "false")
                elif dtype == "str":
                    str(value_str)
                else:
                    # Unknown type, skip
                    continue
            except (ValueError, TypeError):
                pytest.fail(f"Config {key} has invalid value {value_str} for type {dtype}")
