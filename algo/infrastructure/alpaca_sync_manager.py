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
        self._alpaca_key = creds.get("key")
        self._alpaca_secret = creds.get("secret")
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
        """Sync Alpaca positions to database (placeholder for paper trading).

        Fetches current positions from Alpaca API but does NOT write to database.
        This is intentional for paper trading mode — no position sync is needed.

        For production (live trading): Implement actual sync logic to update DB with:
        - New positions imported from Alpaca
        - Positions closed that still exist in database
        - Imported position status updates

        Returns status dict with counts of imported, updated, closed positions.
        Currently: imported=0, updated=0, closed=0 (placeholder behavior).
        """
        from typing import cast

        import requests

        try:
            # Fetch all positions from Alpaca
            url = f"{self._alpaca_base_url}/v2/positions"
            headers = {
                "APCA-API-KEY-ID": self._alpaca_key,
                "APCA-API-SECRET-KEY": self._alpaca_secret,
                "Accept": "application/json",
            }
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            alpaca_positions = cast(list[dict[str, Any]], resp.json())

            imported = 0
            updated = 0
            closed = 0
            orphan_symbols: list[str] = []

            if not alpaca_positions:
                logger.info("No positions in Alpaca account")
                return {
                    "imported": 0,
                    "updated": 0,
                    "closed": 0,
                    "message": "No positions to sync",
                    "orphan_symbols": [],
                }

            logger.warning(
                f"Position sync skipped (paper trading mode). Alpaca has {len(alpaca_positions)} positions. "
                "Production implementation would: sync positions to DB, track closures, manage orphaned symbols."
            )

            return {
                "imported": imported,
                "updated": updated,
                "closed": closed,
                "message": f"Placeholder: Found {len(alpaca_positions)} positions in Alpaca (not synced)",
                "orphan_symbols": orphan_symbols,
            }
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Failed to fetch Alpaca positions for sync: {e}")
            raise

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
            "[ALPACA_SYNC] Position failure recovery not yet fully implemented. "
            f"Found {len(alpaca_positions)} positions in Alpaca but recovery logic is incomplete. "
            "This is a placeholder. Implement actual failure recovery logic before production use."
        )
