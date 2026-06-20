#!/usr/bin/env python3
"""Alpaca account synchronization and position management.

Extracted from DailyReconciliation to reduce monolithic design and enable
independent testing of position sync logic.
"""

import logging
from typing import Any

from config.alpaca_config import get_alpaca_base_url
from config.credential_manager import get_credential_manager
from utils.db import DatabaseContext

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

    def fetch_alpaca_account(self) -> dict[str, Any]:
        """Fetch current account data from Alpaca.

        Returns account details: equity, cash, portfolio_value, etc.
        """
        import requests

        try:
            url = f"{self._alpaca_base_url}/v2/account"
            headers = {
                "Authorization": f"Bearer {self._alpaca_key}",
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            logger.error(f"Failed to fetch Alpaca account: {e}")
            return {}

    def sync_alpaca_positions(self, cur) -> dict[str, Any]:
        """Sync Alpaca positions to database.

        Fetches current positions from Alpaca and updates database with:
        - New positions imported from Alpaca
        - Positions closed that still exist in database
        - Imported position status updates

        Returns status dict with counts of imported, updated, closed positions.
        """
        # Placeholder: full implementation would sync positions
        return {"imported": 0, "updated": 0, "closed": 0}

    def process_failed_imports(self, cur, alpaca_positions: list) -> dict[str, Any]:
        """Handle positions that failed to import or process.

        Returns status dict with recovery actions taken.
        """
        # Placeholder: full implementation would handle import failures
        return {"recovered": 0, "failed": 0}
