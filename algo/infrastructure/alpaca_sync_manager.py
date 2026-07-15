#!/usr/bin/env python3
"""Alpaca account synchronization and position management.

Extracted from DailyReconciliation to reduce monolithic design and enable
independent testing of position sync logic.
"""

import logging
import os
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from algo.trading.executor_strategies import create_execution_mode_strategy
from config.credential_manager import get_credential_manager

logger = logging.getLogger(__name__)


class AlpacaSyncManager:
    """Manages Alpaca account sync: fetching positions, importing positions, processing failures."""

    def __init__(self, config: Any):
        self.config = config
        credential_manager = get_credential_manager()
        creds = credential_manager.get_alpaca_credentials()

        # Fail-fast credential validation: never use .get() with silent defaults
        # Paper trading mode can degrade gracefully without valid Alpaca credentials
        has_key = "key" in creds and bool(creds.get("key"))
        has_secret = "secret" in creds and bool(creds.get("secret"))
        # CRITICAL FIX: Require explicit config - fail-fast if missing
        # No silent fallback to False (which would attempt live trading).
        # NOTE: `config` is an AlgoConfig instance in production, not a plain dict.
        # Two bugs here previously: (1) `isinstance(config, dict)` was always False for
        # it, so this raised unconditionally regardless of whether alpaca_paper_trading
        # was actually configured -- this was the real root cause of
        # AlpacaSyncManager/AlpacaBrokerAdapter construction always failing, which
        # reconciliation.py's __init__ then masked behind its own copy of the same bug.
        # (2) AlgoConfig.__contains__ (`in`) only reflects DB-loaded rows, not
        # AlgoConfig.DEFAULTS, but AlgoConfig.get() correctly falls back to DEFAULTS --
        # so the presence check must be done via .get() returning non-None, not `in`.
        is_paper_trading = config.get("alpaca_paper_trading")
        if is_paper_trading is None:
            raise ValueError(
                "[ALPACA_SYNC] Config missing 'alpaca_paper_trading'. "
                "Trading mode must be explicit (paper vs live). "
                "Check algo_config table has this key."
            )

        if not has_key or not has_secret:
            if is_paper_trading:
                logger.warning(
                    "[ALPACA_SYNC] Alpaca credentials missing or empty. "
                    "Paper trading mode enabled - continuing with empty credentials. "
                    "Reconciliation will use database state only (no live Alpaca API calls)."
                )
                self._alpaca_key = ""
                self._alpaca_secret = ""
            else:
                error_msg = ""
                if not has_key:
                    error_msg += "Alpaca API key missing. "
                if not has_secret:
                    error_msg += "Alpaca API secret missing. "
                raise ValueError(
                    f"[CRITICAL] {error_msg}"
                    "AlpacaSyncManager requires valid credentials for live/auto mode. "
                    "Verify Alpaca credentials are properly configured in Secrets Manager."
                )
        else:
            self._alpaca_key = creds["key"]
            self._alpaca_secret = creds["secret"]

        # Use execution mode from config to determine correct Alpaca endpoint
        if isinstance(self.config, dict):
            execution_mode = self.config.get("execution_mode", "paper")
        else:
            # AlgoConfig object - use get() method, not direct attribute access
            execution_mode = self.config.get("execution_mode", "paper")
        strategy = create_execution_mode_strategy(str(execution_mode).lower())
        configured_url = os.getenv("APCA_API_BASE_URL")
        self._alpaca_base_url = strategy.resolve_base_url(configured_url)

        # FIX: Create persistent session with connection pooling to prevent socket exhaustion
        self._session = requests.Session()
        retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
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

        try:
            url = f"{self._alpaca_base_url}/v2/account"
            headers = {
                "APCA-API-KEY-ID": self._alpaca_key,
                "APCA-API-SECRET-KEY": self._alpaca_secret,
                "Accept": "application/json",
            }
            # FAIL-FAST: API timeout must be explicitly configured, never guessed
            timeout = self.config.get("api_request_timeout_seconds")
            if timeout is None:
                raise ValueError(
                    "CRITICAL: api_request_timeout_seconds config missing. "
                    "API requests require explicit timeout configuration. "
                    "Check config and ensure api_request_timeout_seconds is set."
                )
            response = self._session.get(url, headers=headers, timeout=timeout)
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
            # FAIL-FAST: API timeout must be explicitly configured, never guessed
            timeout = self.config.get("api_request_timeout_seconds")
            if timeout is None:
                raise ValueError(
                    "CRITICAL: api_request_timeout_seconds config missing. "
                    "API requests require explicit timeout configuration. "
                    "Check config and ensure api_request_timeout_seconds is set."
                )
            response = self._session.get(url, headers=headers, timeout=timeout)
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

        # Mark positions as closed if they exist in DB but not in Alpaca.
        # BUG FIX: `symbol NOT IN %s` with the empty-set placeholder `(None,)` is a SQL
        # NULL-trap -- `x NOT IN (NULL)` is never TRUE (it's UNKNOWN) for any x, so this
        # silently closed zero rows every time Alpaca legitimately had zero open
        # positions, leaving stale "open" rows in algo_positions forever (confirmed live:
        # a position closed at the broker weeks ago was still "open" in our DB, 7+ days
        # stale). Use `!= ALL(%s)` with a real list instead -- psycopg2 adapts a list to
        # a SQL array, and `col != ALL(ARRAY[])` correctly matches every row when the
        # array is empty.
        try:
            cur.execute(
                """
                UPDATE algo_positions
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE symbol != ALL(%s) AND status = 'open'
            """,
                (list(alpaca_symbols),),
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

        # Sync untracked positions to database (NEW: track broker-held positions)
        # These are positions in Alpaca but not entered by algo (manual, pre-existing, etc.)
        untracked_count = 0
        untracked_closed_count = 0

        if orphan_symbols:
            for symbol in orphan_symbols:
                # Find the position data from alpaca_positions list
                pos_data = next((p for p in alpaca_positions if p.get("symbol") == symbol), None)
                if not pos_data:
                    continue

                qty_float = float(pos_data.get("qty", 0))
                current_price = pos_data.get("current_price")
                position_value = qty_float * float(current_price) if current_price else None

                try:
                    # Check if position already exists
                    cur.execute("SELECT id FROM algo_untracked_positions WHERE symbol = %s LIMIT 1", (symbol,))
                    existing = cur.fetchone()

                    if existing:
                        # Update existing untracked position
                        cur.execute(
                            """
                            UPDATE algo_untracked_positions
                            SET quantity = %s,
                                current_price = %s,
                                position_value = %s,
                                updated_at = CURRENT_TIMESTAMP,
                                last_seen_at = CURRENT_TIMESTAMP
                            WHERE symbol = %s
                        """,
                            (qty_float, float(current_price) if current_price else None, position_value, symbol),
                        )
                    else:
                        # Insert new untracked position
                        cur.execute(
                            """
                            INSERT INTO algo_untracked_positions
                            (symbol, quantity, current_price, position_value, detected_at, updated_at, last_seen_at)
                            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """,
                            (symbol, qty_float, float(current_price) if current_price else None, position_value),
                        )

                    if cur.rowcount > 0:
                        untracked_count += 1
                except Exception as e:
                    logger.error(f"[POSITION_SYNC] Failed to sync untracked position {symbol}: {e}")
                    # Don't raise here, continue syncing other untracked positions

        # Mark untracked positions as closed if they're no longer in Alpaca
        # (haven't been seen in the last sync)
        try:
            cur.execute(
                """
                UPDATE algo_untracked_positions
                SET updated_at = CURRENT_TIMESTAMP
                WHERE symbol != ALL(%s)
            """,
                (list(orphan_symbols),),
            )
            untracked_closed_count = cur.rowcount
        except Exception as e:
            logger.warning(f"[POSITION_SYNC] Failed to mark closed untracked positions: {e}")

        if untracked_count > 0 or untracked_closed_count > 0:
            logger.info(
                f"[POSITION_SYNC] Synced {untracked_count} untracked positions, "
                f"marked {untracked_closed_count} as stale (not seen in Alpaca)"
            )

        return {
            "message": f"Synced {synced_count} algo positions, marked {closed_count} as closed. "
            f"Tracked {untracked_count} untracked positions.",
            "orphan_symbols": orphan_symbols,
            "synced_count": synced_count,
            "closed_count": closed_count,
            "untracked_count": untracked_count,
            "untracked_closed_count": untracked_closed_count,
        }

    def process_failed_imports(self, cur: Any, alpaca_positions: list[Any]) -> dict[str, Any]:
        """Handle positions that failed to import or process.

        Production-ready recovery: Retries failed imports with fresh Alpaca data.
        Validates data completeness before retry to prevent stale/degraded data.
        Marks unrecoverable failures for operator review.

        Args:
            cur: Database cursor
            alpaca_positions: Current list of positions from Alpaca

        Returns status dict with recovery attempt details and message.

        Raises RuntimeError: Only if Alpaca API is completely unavailable (fail-fast).
        """
        if not alpaca_positions:
            raise RuntimeError(
                "[ALPACA_SYNC] Cannot reconcile failed imports: Alpaca position data unavailable. "
                "This indicates either Alpaca credentials failed or API is down. "
                "Cannot proceed with position recovery without authoritative Alpaca state. "
                "Check Alpaca API status and credentials before resuming trading."
            )

        # Map Alpaca positions by symbol for quick lookup
        alpaca_map = {pos.get("symbol"): pos for pos in alpaca_positions if pos.get("symbol")}

        # Query failed imports from database
        try:
            cur.execute("SELECT symbol, retry_count FROM alpaca_import_failures WHERE resolved = FALSE LIMIT 100")
            failed_symbols = {row[0]: row[1] for row in cur.fetchall()}
        except Exception as e:
            logger.warning(f"[ALPACA_SYNC] Could not query failed imports table: {e}. Skipping recovery.")
            return {
                "message": "Failed to query import failures — recovery skipped",
                "recovery_attempted": False,
                "recovered_count": 0,
                "failed_count": 0,
            }

        if not failed_symbols:
            logger.info("[ALPACA_SYNC] No failed imports to recover")
            return {
                "message": "No failed imports found",
                "recovery_attempted": True,
                "recovered_count": 0,
                "failed_count": 0,
            }

        # Identify which failed symbols are retryable (still in Alpaca AND have retry budget)
        retryable = {sym: count for sym, count in failed_symbols.items() if sym in alpaca_map and count < 3}
        unretryable = {sym: count for sym, count in failed_symbols.items() if sym not in alpaca_map or count >= 3}

        logger.info(
            f"[ALPACA_SYNC] Import recovery: {len(retryable)} retryable, {len(unretryable)} exhausted/not-in-alpaca"
        )

        # Validate Alpaca data completeness before retry
        recovered_count = 0
        skipped_reasons: dict[str, int] = {}

        for symbol in retryable:
            pos = alpaca_map[symbol]
            qty = pos.get("qty")
            avg_entry = pos.get("avg_entry_price")
            cur_price = pos.get("current_price")
            market_value = pos.get("market_value")

            # Required fields for position recovery
            if not all([qty is not None, avg_entry is not None, cur_price is not None, market_value is not None]):
                reason = (
                    f"incomplete_data:"
                    f"qty={qty is not None},avg_entry={avg_entry is not None},"
                    f"cur_price={cur_price is not None},market_value={market_value is not None}"
                )
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
                continue

            try:
                # Validate numeric values
                qty_float = float(qty)
                avg_entry_float = float(avg_entry)
                cur_price_float = float(cur_price)
                market_value_float = float(market_value)

                # Skip zero/negative quantities (long-only algo)
                if qty_float <= 0:
                    skipped_reasons["zero_or_negative_qty"] = skipped_reasons.get("zero_or_negative_qty", 0) + 1
                    continue

                # Skip invalid prices
                if avg_entry_float <= 0 or cur_price_float <= 0:
                    skipped_reasons["invalid_price"] = skipped_reasons.get("invalid_price", 0) + 1
                    continue

                # Skip zero/negative market value
                if market_value_float <= 0:
                    skipped_reasons["zero_or_negative_market_value"] = (
                        skipped_reasons.get("zero_or_negative_market_value", 0) + 1
                    )
                    continue

                # Data is valid — increment retry count
                cur.execute(
                    "UPDATE alpaca_import_failures SET retry_count = retry_count + 1, "
                    "last_retry = CURRENT_TIMESTAMP WHERE symbol = %s",
                    (symbol,),
                )
                recovered_count += 1
                logger.info(
                    f"[ALPACA_SYNC] Recovery retry #{failed_symbols[symbol] + 1} for {symbol}: "
                    f"qty={qty_float:.0f}, avg_entry=${avg_entry_float:.2f}, "
                    f"cur_price=${cur_price_float:.2f}, market_value=${market_value_float:.2f}"
                )

            except (ValueError, TypeError) as e:
                skipped_reasons[f"numeric_conversion_error:{type(e).__name__}"] = (
                    skipped_reasons.get(f"numeric_conversion_error:{type(e).__name__}", 0) + 1
                )
                continue

        # Mark unretryable as resolved to prevent infinite retry loops
        if unretryable:
            try:
                for symbol in unretryable:
                    cur.execute(
                        "UPDATE alpaca_import_failures SET resolved = TRUE WHERE symbol = %s",
                        (symbol,),
                    )
                logger.warning(
                    f"[ALPACA_SYNC] Marked {len(unretryable)} unretryable imports as resolved: "
                    f"{', '.join(list(unretryable.keys())[:10])}{'...' if len(unretryable) > 10 else ''}"
                )
            except Exception as e:
                logger.error(f"[ALPACA_SYNC] Could not mark unretryable imports as resolved: {e}")

        return {
            "message": (f"Recovery: {recovered_count}/{len(retryable)} retried, {len(unretryable)} marked resolved"),
            "recovery_attempted": True,
            "recovered_count": recovered_count,
            "unretryable_count": len(unretryable),
            "skipped_reasons": skipped_reasons,
        }
