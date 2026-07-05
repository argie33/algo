#!/usr/bin/env python3
"""Alpaca account synchronization and position management.

Extracted from DailyReconciliation to reduce monolithic design and enable
independent testing of position sync logic.
"""

import logging
import os
from typing import Any

import requests

from algo.trading.executor_strategies import create_execution_mode_strategy
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

        # Use execution mode from config to determine correct Alpaca endpoint
        execution_mode = self.config.get("execution_mode", "paper") if isinstance(self.config, dict) else self.config.execution_mode
        strategy = create_execution_mode_strategy(str(execution_mode).lower())
        configured_url = os.getenv("APCA_API_BASE_URL")
        self._alpaca_base_url = strategy.resolve_base_url(configured_url)

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

        Fetches open positions from Alpaca and updates database:
        - New positions are imported as algo_positions
        - Positions closed in Alpaca are marked as closed
        - Imported position status is tracked

        Returns:
            dict with:
            - message: str, summary of sync operation
            - orphan_symbols: list[str], symbols in Alpaca but not in DB
            - synced_count: int, number of positions synchronized
            - closed_count: int, number of positions marked as closed

        Raises:
            RuntimeError: If Alpaca API fails or database error
        """
        try:
            self.fetch_alpaca_account()
        except Exception as e:
            raise RuntimeError(f"[POSITION_SYNC] Failed to fetch Alpaca account: {e}") from e

        # Fetch positions from Alpaca
        try:
            url = f"{self._alpaca_base_url}/v2/positions"
            headers = {
                "APCA-API-KEY-ID": self._alpaca_key,
                "APCA-API-SECRET-KEY": self._alpaca_secret,
                "Accept": "application/json",
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            alpaca_positions = response.json()
        except Exception as e:
            raise RuntimeError(f"[POSITION_SYNC] Failed to fetch positions from Alpaca: {e}") from e

        if not isinstance(alpaca_positions, list):
            raise RuntimeError(f"[POSITION_SYNC] Alpaca positions API returned non-list: {type(alpaca_positions)}")

        # Update database with current Alpaca positions
        synced_count = 0
        closed_count = 0
        alpaca_symbols = set()

        for pos in alpaca_positions:
            symbol = pos.get("symbol")
            qty = pos.get("qty")
            # Alpaca positions API uses avg_entry_price, not avg_fill_price
            avg_entry_price = pos.get("avg_entry_price")

            if not symbol or qty is None or avg_entry_price is None:
                logger.warning(f"[POSITION_SYNC] Skipping malformed position: {pos}")
                continue

            qty_float = float(qty)
            if qty_float <= 0:
                # Long-only algo: short or zero positions from Alpaca are anomalous.
                # Close them in DB immediately rather than updating with negative values.
                logger.warning(
                    f"[POSITION_SYNC] Short/zero position {symbol} qty={qty_float:.4f} — "
                    "closing in DB (long-only algo does not hold short positions)"
                )
                cur.execute(
                    "UPDATE algo_positions SET status='closed', closed_at=CURRENT_TIMESTAMP, "
                    "updated_at=CURRENT_TIMESTAMP WHERE symbol=%s AND status='open'",
                    (symbol,),
                )
                continue

            alpaca_symbols.add(symbol)
            current_price = pos.get("current_price")
            position_value = qty_float * float(current_price) if current_price else None

            # Update existing algo-tracked position — never INSERT from Alpaca sync.
            # The algo's entry execution is the source of truth for position creation.
            # Inserting with asset_id as position_id creates duplicate NULL-stop records
            # that trip the circuit breaker. Only update price/qty for existing positions.
            try:
                cur.execute(
                    """
                    UPDATE algo_positions
                    SET quantity = %s,
                        current_price = %s,
                        position_value = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s AND status = 'open'
                """,
                    (
                        qty_float,
                        float(current_price) if current_price else None,
                        float(position_value) if position_value else None,
                        symbol,
                    ),
                )
                if cur.rowcount > 0:
                    synced_count += 1
                else:
                    logger.warning(
                        f"[POSITION_SYNC] No existing open position for {symbol} — skipping (not algo-tracked)"
                    )
            except Exception as e:
                logger.error(f"[POSITION_SYNC] Failed to update position {symbol}: {e}")
                raise RuntimeError(f"[POSITION_SYNC] Database error updating position {symbol}: {e}") from e

        # Mark positions as closed if they exist in DB but not in Alpaca
        try:
            cur.execute(
                """
                UPDATE algo_positions
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE symbol NOT IN %s AND status = 'open'
            """,
                (tuple(alpaca_symbols) if alpaca_symbols else (None,),),
            )
            closed_count = cur.rowcount
        except Exception as e:
            logger.error(f"[POSITION_SYNC] Failed to mark closed positions: {e}")
            raise RuntimeError(f"[POSITION_SYNC] Database error marking closed positions: {e}") from e

        # Remove stale Alpaca-imported rows that have no algo trade association.
        # These were created by a prior sync bug that INSERTed positions using Alpaca's
        # asset_id (UUID) as position_id. They have NULL current_stop_price and no
        # trade_ids_arr, which trips the circuit breaker's missing-stop check.
        # GUARD: only delete rows where position_id is a UUID (old bug signature).
        # Valid algo positions may also lack current_stop_price but must NOT be deleted.
        cur.execute("""
            DELETE FROM algo_positions
            WHERE status = 'open'
              AND current_stop_price IS NULL
              AND (trade_ids_arr IS NULL OR array_length(trade_ids_arr, 1) IS NULL)
              AND position_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        """)
        cleaned_count = cur.rowcount
        if cleaned_count > 0:
            logger.info(
                f"[POSITION_SYNC] Removed {cleaned_count} stale Alpaca-imported positions with no trade associations"
            )

        # Identify orphan positions (in Alpaca but not in our algo_positions table)
        cur.execute("""
            SELECT DISTINCT symbol FROM algo_positions WHERE status = 'open'
        """)
        db_symbols = {row[0] for row in cur.fetchall()}
        orphan_symbols = list(alpaca_symbols - db_symbols)

        return {
            "message": f"Synced {synced_count} positions, marked {closed_count} as closed",
            "orphan_symbols": orphan_symbols,
            "synced_count": synced_count,
            "closed_count": closed_count,
        }

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
