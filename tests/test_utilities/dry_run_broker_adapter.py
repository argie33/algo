#!/usr/bin/env python3
"""Dry-run broker adapter for testing without live broker connections.

TEST-ONLY: This module is isolated in tests/ directory and should never be
imported in production code. Importing this adapter requires explicit test mode
enablement via ORCHESTRATOR_DRY_RUN=true environment variable.

Returns synthetic portfolio data ($100k) for testing orchestration logic without
Alpaca credentials or live market data.
"""

import os
from typing import Any

from algo.infrastructure.broker_adapter import BrokerAdapter


class DryRunBrokerAdapter(BrokerAdapter):
    """Mock broker for dry-run testing when explicitly enabled.

    Returns synthetic data for testing orchestration logic without live Alpaca API calls.
    CRITICAL: Must only be used when ORCHESTRATOR_DRY_RUN=true is explicitly set.

    Safety check: Raises RuntimeError if instantiated outside test mode.
    """

    def __init__(self) -> None:
        """Initialize adapter with test mode validation."""
        # CRITICAL SAFETY: Verify test mode is enabled before allowing instantiation
        dry_run_enabled = os.getenv("ORCHESTRATOR_DRY_RUN", "false").lower() in ("true", "1", "yes")
        if not dry_run_enabled:
            raise RuntimeError(
                "[TEST_MODE_REQUIRED] DryRunBrokerAdapter requires ORCHESTRATOR_DRY_RUN=true. "
                "This adapter returns mock data and must never be used in production. "
                "Enable ORCHESTRATOR_DRY_RUN=true to use in development/testing only."
            )

        # Verify environment is development/test
        env = os.getenv("ENVIRONMENT", "unknown").lower()
        if env not in ("development", "test", "local"):
            raise RuntimeError(
                f"[TEST_MODE_ENVIRONMENT] DryRunBrokerAdapter requires ENVIRONMENT=development|test|local. "
                f"Got ENVIRONMENT={env}. Mock data cannot be used in {env} environment."
            )

    @property
    def alpaca_key(self) -> str | None:
        """Mock Alpaca API key (not used in dry-run mode)."""
        return None

    @property
    def alpaca_secret(self) -> str | None:
        """Mock Alpaca API secret (not used in dry-run mode)."""
        return None

    @property
    def alpaca_base_url(self) -> str | None:
        """Mock Alpaca base URL (not used in dry-run mode)."""
        return None

    def fetch_account(self) -> dict[str, Any]:
        """Return mock account data for testing.

        CRITICAL: This is synthetic test data ($100k hardcoded portfolio).
        Must never be used for real trading calculations.
        """
        return {
            "portfolio_value": 100000.0,  # Synthetic test value
            "cash": 50000.0,  # Synthetic test value
            "equity": 50000.0,  # Synthetic test value
            "_is_mock_data": True,  # Mark as fake data
            "_is_testing_only": True,  # Explicit testing marker
        }

    def fetch_portfolio_history(self) -> list[float]:
        """Return empty portfolio history (no historical data in dry-run mode)."""
        return []

    def fetch_closed_orders(self, since: Any | None = None) -> list[dict[str, Any]]:
        """Return empty closed orders (no order history in dry-run mode)."""
        return []

    def fetch_initial_capital(self) -> float | None:
        """Return None (initial capital not tracked in dry-run mode)."""
        return None

    def sync_positions(self, cur: Any) -> dict[str, Any]:
        """Return empty position sync result (no positions in dry-run mode)."""
        return {"imported": 0, "updated": 0, "closed": 0}
