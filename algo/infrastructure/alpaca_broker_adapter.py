#!/usr/bin/env python3
"""Alpaca broker adapter - implementation of BrokerAdapter for Alpaca broker."""

import logging
from typing import Any

import requests

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager
from algo.infrastructure.broker_adapter import BrokerAdapter


logger = logging.getLogger(__name__)


class AlpacaBrokerAdapter(BrokerAdapter):
    """Alpaca broker implementation of BrokerAdapter interface.

    Wraps AlpacaSyncManager to provide the common broker interface,
    enabling DailyReconciliation to work with any broker via BrokerAdapter.
    """

    def __init__(self, config: Any):
        """Initialize Alpaca adapter with configuration."""
        self.config = config
        self.alpaca_sync = AlpacaSyncManager(config)

    @property
    def alpaca_key(self) -> str | None:
        """Alpaca API key (Alpaca-specific credential)."""
        return self.alpaca_sync.alpaca_key

    @property
    def alpaca_secret(self) -> str | None:
        """Alpaca API secret (Alpaca-specific credential)."""
        return self.alpaca_sync.alpaca_secret

    @property
    def alpaca_base_url(self) -> str | None:
        """Alpaca API base URL (Alpaca-specific endpoint)."""
        return self.alpaca_sync.alpaca_base_url

    def fetch_account(self) -> dict[str, Any]:
        """Fetch account data from Alpaca REST API.

        Returns dict with portfolio_value, cash, equity, buying_power.
        Raises ValueError if fetch fails or credentials missing.
        """
        if not self.alpaca_sync.alpaca_key or not self.alpaca_sync.alpaca_secret:
            raise RuntimeError(
                "CRITICAL: Alpaca API credentials not available. "
                "Cannot reconcile account without valid credentials. "
                "Reconciliation requires live Alpaca connection."
            )
        try:
            resp = requests.get(
                f"{self.alpaca_sync.alpaca_base_url}/v2/account",
                headers={
                    "APCA-API-KEY-ID": self.alpaca_sync.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_sync.alpaca_secret,
                },
                timeout=self.config.get("api_request_timeout_seconds", 5),
            )
            if resp.status_code == 200:
                data = resp.json()
                cash_val = data.get("cash")
                equity_val = data.get("equity")
                portfolio_value_val = data.get("portfolio_value") or data.get("equity")
                buying_power_val = data.get("buying_power")
                return {
                    "cash": float(cash_val) if cash_val is not None else None,
                    "equity": float(equity_val) if equity_val is not None else None,
                    "portfolio_value": float(portfolio_value_val) if portfolio_value_val is not None else None,
                    "buying_power": float(buying_power_val) if buying_power_val is not None else None,
                }
            raise ValueError(f"Alpaca /v2/account returned HTTP {resp.status_code}: {resp.text[:100]}")
        except (requests.RequestException, requests.Timeout, ValueError, KeyError, AttributeError) as e:
            raise ValueError(f"Could not fetch Alpaca account: {e}") from e

    def sync_positions(self, cur: Any) -> dict[str, Any]:
        """Sync Alpaca positions to database via AlpacaSyncManager.

        Args:
            cur: Database cursor for writing position data

        Returns dict with sync result and optional orphan_symbols list.
        """
        return self.alpaca_sync.sync_alpaca_positions(cur)

    def fetch_portfolio_history(self) -> list[float]:
        """Fetch historical portfolio equity values from Alpaca REST API.

        Returns list of equity values (oldest first), or empty list if unavailable.
        """
        if not self.alpaca_sync.alpaca_key or not self.alpaca_sync.alpaca_secret:
            logger.debug("No Alpaca credentials available for portfolio history fetch")
            return []

        try:
            resp = requests.get(
                f"{self.alpaca_sync.alpaca_base_url}/v2/account/portfolio/history",
                params={"period": "all"},
                headers={
                    "APCA-API-KEY-ID": self.alpaca_sync.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_sync.alpaca_secret,
                },
                timeout=self.config.get("api_request_timeout_seconds", 5),
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "equity" in data:
                    equity_list = data.get("equity")
                    if equity_list:
                        return [float(val) for val in equity_list]
            logger.debug(f"Alpaca portfolio history unavailable (HTTP {resp.status_code})")
            return []
        except (requests.RequestException, requests.Timeout, ValueError, KeyError, TypeError) as e:
            logger.debug(f"Could not fetch Alpaca portfolio history: {e}")
            return []
