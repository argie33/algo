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
                portfolio_value_val = data.get("portfolio_value")

                # CRITICAL: Do NOT silently swap between portfolio_value and equity fields.
                # These may have different meanings in Alpaca API; swapping silently masks which
                # field is actually being used, and could cause incorrect position sizing.
                if portfolio_value_val is None:
                    if equity_val is None:
                        logger.error(
                            "CRITICAL: Alpaca /v2/account response missing both 'portfolio_value' and 'equity' fields. "
                            "Response keys: %s",
                            list(data.keys()),
                        )
                        raise ValueError(
                            "Alpaca /v2/account response missing both 'portfolio_value' and 'equity' fields. "
                            "Cannot determine account portfolio value. "
                            "Check: Alpaca API documentation, account status."
                        )
                    else:
                        logger.error(
                            "CRITICAL: Alpaca /v2/account response missing 'portfolio_value' field. "
                            "Found 'equity' field instead, but these fields may have different meanings. "
                            "Cannot silently swap without verifying API compatibility. "
                            "Response keys: %s",
                            list(data.keys()),
                        )
                        raise ValueError(
                            "Alpaca /v2/account response missing 'portfolio_value' field and only 'equity' available. "
                            "Cannot determine correct portfolio value - 'equity' and 'portfolio_value' may differ. "
                            "Check: Alpaca API documentation for field definitions, account status."
                        )

                buying_power_val = data.get("buying_power")
                return {
                    "cash": float(cash_val) if cash_val is not None else None,
                    "equity": float(equity_val) if equity_val is not None else None,
                    "portfolio_value": float(portfolio_value_val),
                    "buying_power": (float(buying_power_val) if buying_power_val is not None else None),
                }
            raise ValueError(f"Alpaca /v2/account returned HTTP {resp.status_code}: {resp.text[:100]}")
        except (
            requests.RequestException,
            requests.Timeout,
            ValueError,
            KeyError,
            AttributeError,
        ) as e:
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

        Returns list of equity values (oldest first).
        Raises ValueError if credentials missing or fetch fails (fail-fast).
        """
        if not self.alpaca_sync.alpaca_key or not self.alpaca_sync.alpaca_secret:
            raise ValueError(
                "CRITICAL: Alpaca credentials missing. Cannot fetch portfolio history without valid API credentials."
            )

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
                raise ValueError(
                    f"Alpaca portfolio history API returned invalid response: missing 'equity' field. "
                    f"Response keys: {list(data.keys())}"
                )
            raise ValueError(f"Alpaca portfolio history fetch failed with HTTP {resp.status_code}: {resp.text[:150]}")
        except (
            requests.RequestException,
            requests.Timeout,
            ValueError,
            KeyError,
            TypeError,
        ) as e:
            raise ValueError(f"Cannot fetch Alpaca portfolio history: {e}") from e

    def fetch_closed_orders(self, since: Any = None) -> list[dict[str, Any]]:
        """Fetch closed/filled orders from Alpaca REST API.

        Args:
            since: Optional datetime to filter orders after

        Returns:
            List of order dicts from Alpaca API

        Raises ValueError if fetch fails (fail-fast, no silent fallback to empty list).
        """
        if not self.alpaca_sync.alpaca_key or not self.alpaca_sync.alpaca_secret:
            raise ValueError(
                "CRITICAL: Alpaca credentials missing. Cannot fetch closed orders without valid API credentials."
            )

        try:
            url = f"{self.alpaca_sync.alpaca_base_url}/v2/orders"
            params: dict[str, list[str] | str] = {"status": ["filled", "partially_filled"]}
            if since:
                params["after"] = since.isoformat() if hasattr(since, "isoformat") else str(since)

            resp = requests.get(
                url,
                params=params,
                headers={
                    "APCA-API-KEY-ID": self.alpaca_sync.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_sync.alpaca_secret,
                },
                timeout=self.config.get("api_request_timeout_seconds", 5),
            )
            if resp.status_code == 200:
                orders = resp.json()
                if not isinstance(orders, list):
                    raise ValueError(
                        f"Alpaca API returned non-list response for closed orders: {type(orders).__name__}"
                    )
                return orders
            raise ValueError(f"Alpaca closed orders fetch failed with HTTP {resp.status_code}: {resp.text[:150]}")
        except (requests.RequestException, requests.Timeout, ValueError, KeyError) as e:
            raise ValueError(f"Cannot fetch Alpaca closed orders: {e}") from e

    def fetch_initial_capital(self) -> float:
        """Fetch initial portfolio equity from Alpaca portfolio history.

        Returns:
            Initial capital (first equity value) as float.

        Raises ValueError if portfolio history is empty or API fails (fail-fast).
        """
        try:
            history = self.fetch_portfolio_history()
            if not history:
                raise ValueError(
                    "Alpaca portfolio history is empty — cannot determine initial capital. "
                    "Ensure portfolio has at least one historical equity entry."
                )
            return float(history[0])
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"Cannot determine initial capital: {e}") from e
