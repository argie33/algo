"""Pytest configuration for all tests.

This file helps pytest discover and import project modules correctly and provides
shared fixtures for dependency injection testing patterns.

With proper package installation (pip install -e .), explicit path setup shouldn't be needed,
but this provides a safety net for different test execution contexts.
"""

import sys
from pathlib import Path
import pytest
from typing import Dict, Any

# Ensure project root is in sys.path for imports to work
_test_dir = Path(__file__).parent
_project_root = _test_dir.parent

if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Also add lambda/api for Lambda-specific tests
_lambda_api = _project_root / "lambda" / "api"
if str(_lambda_api) not in sys.path:
    sys.path.insert(0, str(_lambda_api))

# Import fixture functions
from tests.test_helpers.config_fixtures import (
    BASE_CONFIG,
    bull_market_config,
    correction_config,
    crisis_config,
    minimal_config,
    strict_risk_config,
    relaxed_risk_config,
    sandbox_config,
)


# ============================================================================
# Pytest Fixtures for Dependency Injection Testing
# ============================================================================

@pytest.fixture
def mock_config_base() -> Dict[str, Any]:
    """Base configuration fixture for standard conditions.

    Use this fixture when you want to test with standard default config.
    """
    return BASE_CONFIG.copy()


@pytest.fixture
def mock_config_bull() -> Dict[str, Any]:
    """Configuration fixture for bull market conditions.

    Use when testing during uptrend (higher risk, higher confidence).
    """
    return bull_market_config()


@pytest.fixture
def mock_config_correction() -> Dict[str, Any]:
    """Configuration fixture for correction/consolidation conditions.

    Use when testing during moderate volatility and mixed signals.
    """
    return correction_config()


@pytest.fixture
def mock_config_crisis() -> Dict[str, Any]:
    """Configuration fixture for crisis/bear market conditions.

    Use when testing capital preservation and defensive behavior.
    """
    return crisis_config()


@pytest.fixture
def mock_config_minimal() -> Dict[str, Any]:
    """Minimal configuration with only essential keys.

    Use for lightweight unit tests that don't need all config keys.
    Faster to create and reason about than full config.
    """
    return minimal_config()


@pytest.fixture
def mock_config_strict_risk() -> Dict[str, Any]:
    """Configuration with very tight risk limits.

    Use for testing circuit breaker and risk control systems.
    """
    return strict_risk_config()


@pytest.fixture
def mock_config_relaxed_risk() -> Dict[str, Any]:
    """Configuration with relaxed risk limits.

    Use for testing edge cases where risk controls might be loose.
    """
    return relaxed_risk_config()


@pytest.fixture
def mock_config_sandbox() -> Dict[str, Any]:
    """Sandbox configuration for integration tests.

    Pre-configured for paper trading and review mode (no actual orders).
    """
    return sandbox_config()


@pytest.fixture
def mock_config_custom(request) -> Dict[str, Any]:
    """Custom configuration fixture parameterized via pytest.

    Usage in test:
        @pytest.mark.parametrize('mock_config_custom', [
            {'base_risk_pct': 0.5, 'max_positions': 5}
        ], indirect=True)
        def test_something(mock_config_custom):
            config = mock_config_custom
    """
    overrides = getattr(request, "param", {})
    config = BASE_CONFIG.copy()
    config.update(overrides)
    return config
