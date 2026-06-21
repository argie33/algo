#!/usr/bin/env python3
"""Broker integration adapter - abstraction layer for different brokers.

Defines a common interface for broker operations, enabling DailyReconciliation
to work with any broker implementation (Alpaca, Interactive Brokers, etc).
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BrokerAdapter(Protocol):
    """Protocol defining the interface all broker adapters must implement."""

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
