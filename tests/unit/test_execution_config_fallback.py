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
    """CRITICAL: No fallback in any mode - config must always be explicit."""
    # Setup: execution_mode is "auto" (production), default_portfolio_value is missing
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "auto",
        "default_portfolio_value": None,  # Config missing
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)

    # CRITICAL: Must always raise RuntimeError. No fallbacks in any mode.
    with pytest.raises(RuntimeError) as exc_info:
        config.get_default_portfolio_value()

    assert "default_portfolio_value config key missing" in str(exc_info.value)
    assert "no fallback" in str(exc_info.value)


def test_default_portfolio_value_dry_run_mode_fails(mock_parent_config):
    """In dry-run mode, no fallback - config must be explicit (fail-fast governance)."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "dry",
        "default_portfolio_value": None,  # Config missing
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)

    # FAIL-FAST: No fallbacks in any mode, even dry-run
    with pytest.raises(RuntimeError) as exc_info:
        config.get_default_portfolio_value()

    assert "default_portfolio_value config key missing" in str(exc_info.value)


def test_default_portfolio_value_paper_mode_fails(mock_parent_config):
    """In paper mode, no fallback - config must be explicit (fail-fast governance)."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "paper",
        "default_portfolio_value": None,  # Config missing
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)

    # FAIL-FAST: No fallbacks in any mode, even paper
    with pytest.raises(RuntimeError) as exc_info:
        config.get_default_portfolio_value()

    assert "default_portfolio_value config key missing" in str(exc_info.value)


def test_default_portfolio_value_review_mode_fails(mock_parent_config):
    """In review mode, no fallback - config must be explicit (fail-fast governance)."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "review",
        "default_portfolio_value": None,  # Config missing
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)

    # FAIL-FAST: No fallbacks in any mode, even review
    with pytest.raises(RuntimeError) as exc_info:
        config.get_default_portfolio_value()

    assert "default_portfolio_value config key missing" in str(exc_info.value)


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


def test_invalid_execution_mode_raises(mock_parent_config):
    """Invalid execution modes raise RuntimeError (fail-fast governance)."""
    mock_parent_config.get.side_effect = lambda key, default=None: {
        "execution_mode": "invalid_mode",
    }.get(key, default)

    config = ExecutionConfig(mock_parent_config)
    # FAIL-FAST: Invalid mode raises, no fallback to 'auto'
    with pytest.raises(RuntimeError) as exc_info:
        config.get_execution_mode()

    assert "Invalid execution_mode 'invalid_mode'" in str(exc_info.value)
    assert "Valid modes are" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
