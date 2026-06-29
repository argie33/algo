#!/usr/bin/env python3
"""Alpaca account synchronization and position management.

Extracted from DailyReconciliation to reduce monolithic design and enable
independent testing of position sync logic.
"""

import logging
from typing import Any

from config.api_endpoints import get_alpaca_base_url
from config.credential_manager import get_credential_manager

logger = logging.getLogger(__name__)


class AlpacaSyncManager:
    """Manages Alpaca account sync: fetching positions, importing positions, processing failures."""

    def __init__(self, config: Any):
        """Initialize with configuration and credentials."""
        self.config = config
        credential_manager = get_credential_manager()
        creds = credential_manager.get_alpaca_credentials()

        # Fail-fast credential validation: never use .get() with silent defaults
        if "key" not in creds:
            raise ValueError(
                "[CRITICAL] Alpaca API key missing from credentials. "
                "AlpacaSyncManager cannot proceed without valid authentication. "
                "Verify Alpaca credentials are properly configured in Secrets Manager."
            )
        if "secret" not in creds:
            raise ValueError(
                "[CRITICAL] Alpaca API secret missing from credentials. "
                "AlpacaSyncManager cannot proceed without valid authentication. "
                "Verify Alpaca credentials are properly configured in Secrets Manager."
            )

        self._alpaca_key = creds["key"]
        self._alpaca_secret = creds["secret"]
        self._alpaca_base_url = get_alpaca_base_url()

    @property
    def alpaca_key(self) -> str | None:
        """Public accessor for Alpaca API key."""
        return self._alpaca_key

    @property
    def alpaca_secret(self) -> str | None:
        """Public accessor for Alpaca API secret."""
        return self._alpaca_secret

    @property
    def alpaca_base_url(self) -> str | None:
        """Public accessor for Alpaca API base URL."""
        return self._alpaca_base_url

    def fetch_alpaca_account(self) -> dict[str, Any]:
        """Fetch current account data from Alpaca.

        Returns account details: equity, cash, portfolio_value, etc.
        """
        from typing import cast

        import requests

        try:
            url = f"{self._alpaca_base_url}/v2/account"
            headers = {
                "APCA-API-KEY-ID": self._alpaca_key,
                "APCA-API-SECRET-KEY": self._alpaca_secret,
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Failed to fetch Alpaca account: {e}")
            raise

    def sync_alpaca_positions(self, cur: Any) -> dict[str, Any]:
        """Sync Alpaca positions to database.

        CRITICAL: This method is currently not implemented.
        Position sync logic must be implemented before production use.

        For production (live trading): Implement actual sync logic to update DB with:
        - New positions imported from Alpaca
        - Positions closed that still exist in database
        - Imported position status updates

        Raises:
            RuntimeError: Position sync logic is not implemented
        """
        raise RuntimeError(
            "[POSITION_SYNC] CRITICAL: sync_alpaca_positions() is not implemented. "
            "Position synchronization between Alpaca and database is REQUIRED for production trading. "
            "Cannot proceed without actual sync implementation. "
            "Implement sync logic that: (1) fetches positions from Alpaca, "
            "(2) imports new positions to database, "
            "(3) marks closed positions as imported."
        )

    def process_failed_imports(self, cur: Any, alpaca_positions: list[Any]) -> dict[str, Any]:
        """Handle positions that failed to import or process.

        Args:
            cur: Database cursor
            alpaca_positions: Current list of positions from Alpaca

        Returns status dict with recovery actions taken and message.

        Raises RuntimeError if position reconciliation cannot proceed (fail-fast).
        """
        if not alpaca_positions:
            raise RuntimeError(
                "[ALPACA_SYNC] Cannot reconcile failed imports: Alpaca position data unavailable. "
                "This indicates either Alpaca credentials failed or API is down. "
                "Cannot proceed with position recovery without authoritative Alpaca state. "
                "Check Alpaca API status and credentials before resuming trading."
            )

        raise RuntimeError(
            "[ALPACA_SYNC] CRITICAL: Position failure recovery not implemented. "
            f"Found {len(alpaca_positions)} positions in Alpaca but recovery logic is NOT implemented. "
            "Cannot proceed with daily reconciliation without failure recovery mechanism. "
            "Implement recovery logic that handles: (1) orphaned positions (in Alpaca but not DB), "
            "(2) mismatch resolution (quantity/price discrepancies), "
            "(3) state synchronization (pending orders, filled orders)."
        )
