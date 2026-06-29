#!/usr/bin/env python3
"""Dry-run adapters for testing without live broker connections.

These adapters are used when ORCHESTRATOR_DRY_RUN=true to enable testing
of orchestration logic without Alpaca credentials.
"""

from typing import Any

from algo.infrastructure.broker_adapter import BrokerAdapter


class DryRunBrokerAdapter(BrokerAdapter):
    """Mock broker for dry-run testing when explicitly enabled.

    Returns synthetic data for testing orchestration logic without live Alpaca API calls.
    Use ONLY when ORCHESTRATOR_DRY_RUN=true environment variable is explicitly set.
    """

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
        """Return mock account data for testing."""
        return {
            "portfolio_value": 100000.0,  # Synthetic test value
            "cash": 50000.0,  # Synthetic test value
            "equity": 50000.0,  # Synthetic test value
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
