#!/usr/bin/env python3
"""Broker integration adapter - abstraction layer for different brokers.

Defines a common interface for broker operations, enabling DailyReconciliation
to work with any broker implementation (Alpaca, Interactive Brokers, etc).
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BrokerAdapter(Protocol):
    """Protocol defining the interface all broker adapters must implement."""

    @property
    def alpaca_key(self) -> str | None:
        """Alpaca API key (None if not available)."""
        ...

    @property
    def alpaca_secret(self) -> str | None:
        """Alpaca API secret (None if not available)."""
        ...

    @property
    def alpaca_base_url(self) -> str | None:
        """Alpaca API base URL (None if not available)."""
        ...

    def fetch_account(self) -> dict[str, Any]:
        """Fetch current account data from broker.

        Returns dict with at least:
            - portfolio_value: float, total account value
            - cash: float, available cash
            - equity: float, total equity
            - buying_power: float (optional)
        """
        ...

    def sync_positions(self, cur: Any) -> dict[str, Any]:
        """Sync open positions from broker to database.

        Args:
            cur: Database cursor for writing position data

        Returns dict with:
            - message: str, summary of sync operation
            - orphan_symbols: list[str] (optional), symbols flagged as orphans
        """
        ...

    def fetch_portfolio_history(self) -> list[float]:
        """Fetch historical portfolio equity values from broker.

        Returns list of equity values (oldest first), or empty list if unavailable.
        """
        ...

    def fetch_closed_orders(self, since: Any | None = None) -> list[dict[str, Any]]:
        """Fetch closed/filled orders from broker.

        Args:
            since: Optional datetime to fetch orders after

        Returns:
            List of order dicts with at minimum symbol, qty, price, filled_at
        """
        ...

    def fetch_initial_capital(self) -> float | None:
        """Fetch initial portfolio equity (first known value from account history).

        Returns:
            Initial capital amount, or None if unavailable
        """
        ...
