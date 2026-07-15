#!/usr/bin/env python3
"""Alpaca broker adapter - implementation of BrokerAdapter for Alpaca broker."""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager
from algo.infrastructure.broker_adapter import BrokerAdapter

logger = logging.getLogger(__name__)


class AlpacaBrokerAdapter(BrokerAdapter):
    """Alpaca broker implementation of BrokerAdapter interface.

    Wraps AlpacaSyncManager to provide the common broker interface,
    enabling DailyReconciliation to work with any broker via BrokerAdapter.
    """

    def __init__(self, config: Any):
        self.config = config
        self.alpaca_sync = AlpacaSyncManager(config)

        # FIX: Create persistent session with connection pooling to prevent socket exhaustion
        # This addresses Alpaca API timeout issues from file descriptor leaks
        self._session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def __del__(self) -> None:
        """Ensure session is closed to release file descriptors."""
        if hasattr(self, "_session"):
            try:
                self._session.close()
            except Exception as e:
                logger.warning(f"Failed to close Alpaca session: {e}")

    def _request_with_retry(
        self, method: str, url: str, max_retries: int = 3, initial_backoff: float = 1.0, **kwargs: Any
    ) -> requests.Response:
        """Execute HTTP request with exponential backoff retry on timeout.

        Uses persistent session with connection pooling to prevent socket exhaustion.
        Implements exponential backoff (1s, 2s, 4s) for transient failures.

        Args:
            method: HTTP method ('get', 'post', etc.)
            url: URL to request
            max_retries: Maximum number of retry attempts (default: 3)
            initial_backoff: Starting backoff in seconds (default: 1.0)
            **kwargs: Additional arguments to pass to session method

        Returns:
            Response object on success

        Raises:
            ValueError: If all retries exhausted or request fails
        """
        backoff = initial_backoff
        last_error = None

        for attempt in range(max_retries):
            try:
                # Use session method (connection pooling enabled) instead of bare requests
                req_method = getattr(self._session, method.lower())
                return req_method(url, **kwargs)
            except (requests.Timeout, requests.ConnectionError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Alpaca API request timeout (attempt {attempt + 1}/{max_retries}), retrying in {backoff}s: {e}"
                    )
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    logger.error(f"Alpaca API request failed after {max_retries} retries: {e}")

        raise ValueError(f"Alpaca API request failed after {max_retries} retries: {last_error}") from last_error

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

    def _get_api_timeout(self) -> float:
        timeout = self.config.get("api_request_timeout_seconds")
        if timeout is None:
            raise ValueError(
                "CRITICAL: Alpaca API request timeout not configured. "
                "Configuration must include 'api_request_timeout_seconds'. "
                "Cannot proceed with API calls without timeout specification."
            )
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError(
                f"CRITICAL: Alpaca API timeout must be positive number, got {timeout}. Invalid configuration."
            )
        return float(timeout)

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
            resp = self._request_with_retry(
                "get",
                f"{self.alpaca_sync.alpaca_base_url}/v2/account",
                headers={
                    "APCA-API-KEY-ID": self.alpaca_sync.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_sync.alpaca_secret,
                },
                timeout=self._get_api_timeout(),
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
            if resp.status_code in (401, 403):
                raise ValueError(
                    f"CRITICAL: Alpaca /v2/account returned HTTP {resp.status_code} (Unauthorized). "
                    f"This indicates authentication failure: either credentials are invalid, or the account is restricted. "
                    f"Cannot proceed without valid broker authentication. "
                    f"Paper mode does not bypass authentication - check API credentials in AWS Secrets Manager."
                )
            raise ValueError(f"Alpaca /v2/account returned HTTP {resp.status_code}: {resp.text[:100]}")
        except (
            requests.RequestException,
            requests.Timeout,
            ValueError,
            KeyError,
            AttributeError,
        ) as e:
            if "401" in str(e) or "403" in str(e):
                raise ValueError(
                    f"CRITICAL: Alpaca API authentication failed ({type(e).__name__}). "
                    f"Cannot determine account status without valid broker authentication. "
                    f"Reconciliation requires either: (1) valid Alpaca credentials in AWS Secrets Manager, "
                    f"or (2) explicit paper mode with valid account state in database. "
                    f"Details: {str(e)[:200]}"
                ) from e
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
            resp = self._request_with_retry(
                "get",
                f"{self.alpaca_sync.alpaca_base_url}/v2/account/portfolio/history",
                params={"period": "all"},
                headers={
                    "APCA-API-KEY-ID": self.alpaca_sync.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_sync.alpaca_secret,
                },
                timeout=self._get_api_timeout(),
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
            List of order dicts from Alpaca API, or empty list in paper mode without credentials

        Raises ValueError if fetch fails (fail-fast, no silent fallback to empty list).
        """
        if not self.alpaca_sync.alpaca_key or not self.alpaca_sync.alpaca_secret:
            # Paper trading without Alpaca credentials - use database state only
            # CRITICAL: Must explicitly check alpaca_paper_trading config (NO FALLBACK TO LIVE TRADING)
            if not isinstance(self.config, dict):
                raise ValueError(
                    "[CONFIG_ERROR] alpaca_paper_trading configuration missing or invalid. "
                    "CRITICAL: Alpaca broker adapter requires explicit paper_trading flag to prevent accidental live trading."
                )

            if "alpaca_paper_trading" not in self.config:
                raise ValueError(
                    "[CONFIG_ERROR] alpaca_paper_trading key missing from configuration. "
                    "CRITICAL: Must explicitly set alpaca_paper_trading=True or False. "
                    "Refusing to default to False (would enable live trading)."
                )

            is_paper_trading = self.config["alpaca_paper_trading"]
            if not isinstance(is_paper_trading, bool):
                raise ValueError(
                    f"[CONFIG_ERROR] alpaca_paper_trading must be bool, got {type(is_paper_trading).__name__}={is_paper_trading}"
                )

            if is_paper_trading:
                logger.warning(
                    "[CLOSED_ORDERS] Alpaca credentials missing (paper mode). "
                    "Using database state for reconciliation - live orders unavailable."
                )
                # Paper mode: explicitly communicate unavailability instead of silent empty list
                raise ValueError(
                    "[PAPER_TRADING] Alpaca orders unavailable - credentials not configured. "
                    "Expected behavior: reconciliation uses database state only."
                )
            else:
                raise ValueError(
                    "CRITICAL: Alpaca credentials missing. Cannot fetch closed orders without valid API credentials."
                )

        try:
            url = f"{self.alpaca_sync.alpaca_base_url}/v2/orders"
            params: dict[str, list[str] | str] = {"status": ["filled", "partially_filled"]}
            if since:
                params["after"] = since.isoformat() if hasattr(since, "isoformat") else str(since)

            resp = self._request_with_retry(
                "get",
                url,
                params=params,
                headers={
                    "APCA-API-KEY-ID": self.alpaca_sync.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_sync.alpaca_secret,
                },
                timeout=self._get_api_timeout(),
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
                    "Alpaca portfolio history is empty - cannot determine initial capital. "
                    "Ensure portfolio has at least one historical equity entry."
                )
            return float(history[0])
        except (ValueError, KeyError, TypeError) as e:
            raise ValueError(f"Cannot determine initial capital: {e}") from e
