"""Tests for ExecutionConfig fallback portfolio value safeguards.

Ensures the $100k hardcoded fallback is only used in safe modes (dry-run/paper/review)
and never in production (auto) mode.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.infrastructure.config.execution_config import ExecutionConfig


@pytest.fixture
def mock_parent_config():
    """Create a mock parent AlgoConfig."""
    parent = MagicMock()
    return parent


def test_default_portfolio_value_production_mode_fails(mock_parent_config):
    """CRITICAL: $100k fallback must be rejected in production (auto) mode."""
    # Setup: execution_mode is "auto" (production), default_portfolio_value is missing
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "auto",
        "default_portfolio_value": None,  # Config missing
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)

    # CRITICAL: Must raise RuntimeError, not silently use $100k
    with pytest.raises(RuntimeError) as exc_info:
        config.get_default_portfolio_value()

    assert "default_portfolio_value config key missing" in str(exc_info.value)
    assert "Cannot use hardcoded $100k default in production (auto) mode" in str(exc_info.value)


def test_default_portfolio_value_dry_run_mode_uses_fallback(mock_parent_config, caplog):
    """In dry-run mode, $100k fallback is allowed with warning."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "dry",
        "default_portfolio_value": None,  # Config missing
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)

    # In dry-run mode, fallback is allowed
    value = config.get_default_portfolio_value()
    assert value == 100000.0

    # Must log a warning
    assert "[EXECUTION_CONFIG] Using hardcoded default portfolio value" in caplog.text


def test_default_portfolio_value_paper_mode_uses_fallback(mock_parent_config):
    """In paper mode, $100k fallback is allowed."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "paper",
        "default_portfolio_value": None,  # Config missing
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)
    value = config.get_default_portfolio_value()
    assert value == 100000.0


def test_default_portfolio_value_review_mode_uses_fallback(mock_parent_config):
    """In review mode, $100k fallback is allowed."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "review",
        "default_portfolio_value": None,  # Config missing
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)
    value = config.get_default_portfolio_value()
    assert value == 100000.0


def test_default_portfolio_value_explicit_value_overrides_fallback(mock_parent_config):
    """When config has explicit value, it's always used (regardless of mode)."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "auto",
        "default_portfolio_value": 250000.0,  # Explicit config
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)
    value = config.get_default_portfolio_value()
    assert value == 250000.0  # Uses explicit value, not $100k


def test_default_portfolio_value_type_conversion(mock_parent_config):
    """Explicit values are converted to float."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "auto",
        "default_portfolio_value": "500000",  # String from config
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)
    value = config.get_default_portfolio_value()
    assert value == 500000.0
    assert isinstance(value, float)


def test_execution_config_full_dict(mock_parent_config):
    """Full execution config includes portfolio value."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "auto",
        "alpaca_paper_trading": False,
        "max_trades_per_day": 5,
        "default_portfolio_value": 100000.0,
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)
    cfg_dict = config.get_execution_config()

    assert cfg_dict["mode"] == "auto"
    assert cfg_dict["paper_trading"] is False
    assert cfg_dict["max_trades_per_day"] == 5
    assert cfg_dict["default_portfolio_value"] == 100000.0


def test_invalid_execution_mode_defaults_to_auto(mock_parent_config):
    """Invalid execution modes default to 'auto' (safe)."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "invalid_mode",
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)
    mode = config.get_execution_mode()
    assert mode == "auto"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
