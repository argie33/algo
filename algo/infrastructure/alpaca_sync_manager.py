#!/usr/bin/env python3
"""Alpaca account synchronization and position management.

Extracted from DailyReconciliation to reduce monolithic design and enable
independent testing of position sync logic.
"""

import json
import logging
import os
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from algo.config.credential_manager import get_algo_owner_cognito_sub, get_credential_manager
from algo.trading.executor_strategies import create_execution_mode_strategy
from utils.db.advisory_locks import ALGO_POSITIONS_LOCK_ID, acquire_advisory_lock, release_advisory_lock

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
            execution_mode = self.config.get("execution_mode")
        else:
            # AlgoConfig object - use get() method, not direct attribute access
            execution_mode = self.config.get("execution_mode")

        if execution_mode is None:
            raise ValueError(
                "[ALPACA_SYNC_MANAGER CRITICAL] execution_mode config missing. "
                "Cannot determine Alpaca endpoint (live vs paper). "
                "Set explicit execution_mode in algo_config table."
            )
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
        except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
            logger.error(f"Failed to fetch Alpaca account: {e}")
            raise

    def _sync_untracked_positions(
        self, cur: Any, orphan_symbols: list[str], alpaca_positions: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Sync untracked broker positions to database.

        Args:
            cur: Database cursor
            orphan_symbols: Symbols in Alpaca but not in algo_positions table
            alpaca_positions: List of position data from Alpaca API

        Returns:
            tuple of (untracked_count, untracked_closed_count)
        """
        untracked_count = 0
        untracked_closed_count = 0
        newly_detected: list[tuple[str, float, float]] = []

        if orphan_symbols:
            for symbol in orphan_symbols:
                pos_data = next((p for p in alpaca_positions if p.get("symbol") == symbol), None)
                if not pos_data:
                    continue

                if "qty" not in pos_data or pos_data["qty"] is None:
                    logger.warning(f"[ALPACA_SYNC] Missing qty for position {symbol}")
                    continue
                qty_float = float(pos_data["qty"])
                if "current_price" not in pos_data or pos_data["current_price"] is None:
                    logger.warning(f"[ALPACA_SYNC] Missing current_price for position {symbol}")
                    continue
                current_price = pos_data["current_price"]
                position_value = qty_float * float(current_price)

                try:
                    cur.execute(
                        "SELECT id FROM algo_untracked_positions WHERE symbol = %s LIMIT 1",
                        (symbol,),
                    )
                    existing = cur.fetchone()

                    if existing:
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
                            (
                                qty_float,
                                # BUG FOUND 2026-08-16: `if current_price else None` treats a
                                # legitimate current_price=0.0 as falsy, silently writing NULL
                                # instead of 0.0 - same anti-pattern this codebase already
                                # identified and fixed elsewhere for financial fields (see
                                # lambda/api/routes/algo_handlers/dashboard.py's "FIX: Use
                                # explicit None checks instead of falsy checks (0.0 is a valid
                                # price)"). current_price is already guaranteed non-None here
                                # (checked at the top of this loop), but explicit is not None
                                # matches this codebase's established convention and is correct
                                # regardless of that upstream guarantee.
                                float(current_price) if current_price is not None else None,
                                position_value,
                                symbol,
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO algo_untracked_positions
                            (symbol, quantity, current_price, position_value, cognito_sub, detected_at, updated_at, last_seen_at)
                            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """,
                            (
                                symbol,
                                qty_float,
                                float(current_price) if current_price is not None else None,
                                position_value,
                                get_algo_owner_cognito_sub(),
                            ),
                        )
                        # CRITICAL: this is a real broker position (real shares, real dollars)
                        # with no algo_trades/algo_positions row at all - no stop-loss, no exit
                        # management, no risk-limit accounting will ever apply to it, because
                        # every part of this system except this sync loop assumes a position it
                        # doesn't know about doesn't exist. Before this fix, detecting one here
                        # only wrote a DB row nobody actively watches (dashboard/panels/health.py
                        # excludes this table from its staleness alarms, and does not check its
                        # row count either) - a real orphaned position could sit silently for
                        # days. Notify only on first detection (this branch, not the UPDATE
                        # above) so an already-known, still-unresolved position doesn't spam an
                        # alert every reconciliation cycle.
                        newly_detected.append((symbol, qty_float, position_value))

                    if cur.rowcount > 0:
                        untracked_count += 1
                except Exception as e:
                    raise RuntimeError(
                        f"[POSITION_SYNC] Failed to sync untracked position {symbol}: {e}. "
                        f"Database write error during position reconciliation. Cannot proceed with incomplete position sync. "
                        f"Alpaca and database position state must remain synchronized."
                    ) from e

        if newly_detected:
            try:
                from algo.reporting.notifications import notify

                details_str = ", ".join(f"{sym}: {qty}sh (${val:,.2f})" for sym, qty, val in newly_detected)
                notify(
                    "critical",
                    title="Untracked Broker Position(s) Detected",
                    message=(
                        f"{len(newly_detected)} broker position(s) exist with no matching "
                        f"algo_trades/algo_positions record - no stop-loss or exit management "
                        f"applies to them: {details_str}. Investigate immediately: check "
                        "algo_untracked_positions and whether these need manual entry/exit."
                    ),
                )
            except Exception as e:
                # CRITICAL: Operators must be notified of untracked broker positions
                # Silent notification failure means operators won't know about orphaned positions
                logger.critical(f"[POSITION_SYNC CRITICAL] Failed to send untracked-position alert: {e}", exc_info=True)
                raise RuntimeError(
                    f"[POSITION_SYNC] Failed to notify operators of untracked positions: {e}. "
                    f"Untracked broker positions require immediate investigation. "
                    f"Cannot silently proceed without alerting - positions may be at risk without stop-loss protection."
                ) from e

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
            raise RuntimeError(
                f"[POSITION_SYNC] Failed to mark closed untracked positions: {e}. "
                f"Cannot mark stale untracked positions as closed - position tracking state would be incomplete. "
                f"Reconciliation integrity requires all position updates to succeed."
            ) from e

        if untracked_count > 0 or untracked_closed_count > 0:
            logger.info(
                f"[POSITION_SYNC] Synced {untracked_count} untracked positions, "
                f"marked {untracked_closed_count} as stale"
            )

        return untracked_count, untracked_closed_count

    def sync_alpaca_positions(self, cur: Any) -> dict[str, Any]:
        """Sync Alpaca positions to database - advisory-lock-guarded wrapper.

        This writes algo_positions (status/quantity/price) - the same table
        executor.py's entry/exit writes guard with ALGO_POSITIONS_LOCK_ID
        (see executor.py:611-617, _with_cursor(acquire_locks=True)) - but this
        Phase 4 reconciliation path previously wrote without taking that lock.
        Not exploitable in production (orchestrator.py's _acquire_run_lock already
        serializes phases within one run, and no other production process writes
        these tables), but this local dev environment has multiple concurrent
        sessions writing to the same DB outside any run lock, so the same
        defense-in-depth this table's other writers already have is worth
        matching here too. See memory: session_2026-07-27_order_edge_case_audit.
        """
        acquire_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
        try:
            return self._sync_alpaca_positions_impl(cur)
        finally:
            release_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")

    def _sync_alpaca_positions_impl(self, cur: Any) -> dict[str, Any]:
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

        FIX (Session 2026-08-02): Graceful credential failure in paper mode.
        Paper mode can operate without Alpaca credentials (trades exist only in DB).
        Skip sync if credentials missing in paper/review mode, fail-hard only in live.

        BUG FOUND 2026-08-11: this docstring always said "paper/review mode", but the check
        below only ever tested `== "paper"` - "review" was never actually included, and
        neither was "dry" (this system's default outside-market-hours mode, added to the
        codebase's mode vocabulary after this check was written - same gap already fixed
        tonight in executor.py/market_events.py's credential-fetch handling). Both fell
        through to the fail-hard `else` branch, crashing position sync whenever real Alpaca
        credentials happened to be unavailable in dry or review mode.
        """
        is_paper_mode = self.config.get("execution_mode") in ("paper", "dry", "review")

        # Check if Alpaca credentials are available
        if not self._alpaca_key or not self._alpaca_secret:
            if is_paper_mode:
                # Paper mode can work without Alpaca (trades are simulated, not real)
                logger.warning(
                    "[POSITION_SYNC] Alpaca credentials not available in paper mode. "
                    "Skipping position sync (trades exist in database, not in Alpaca account)."
                )
                return {
                    "message": "Position sync skipped (paper mode, no Alpaca credentials)",
                    "orphan_symbols": [],
                    "synced_count": 0,
                    "closed_count": 0,
                }
            else:
                # Live mode requires Alpaca credentials - fail-hard
                raise RuntimeError(
                    "[POSITION_SYNC] Alpaca credentials missing in live mode. "
                    "Cannot sync positions without valid APCA_API_KEY_ID and APCA_API_SECRET_KEY. "
                    "Set credentials before running live trading."
                )

        try:
            self.fetch_alpaca_account()
        except Exception as e:
            if is_paper_mode:
                # Paper mode can continue without account fetch
                logger.warning(f"[POSITION_SYNC] Failed to fetch Alpaca account in paper mode: {e}. Continuing...")
                return {
                    "message": f"Position sync failed (paper mode allows degradation): {e}",
                    "orphan_symbols": [],
                    "synced_count": 0,
                    "closed_count": 0,
                }
            else:
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
                    f"[POSITION_SYNC] Short/zero position {symbol} qty={qty_float:.4f} - "
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
            # BUG FOUND 2026-08-16: `if current_price else None` treats a legitimate
            # current_price=0.0 as falsy, silently dropping position_value to None instead of
            # computing 0.0 - same anti-pattern already fixed elsewhere in this codebase for
            # financial fields (0.0 is a valid price, not "missing").
            position_value = qty_float * float(current_price) if current_price is not None else None

            # Update existing algo-tracked position - never INSERT from Alpaca sync.
            # The algo's entry execution is the source of truth for position creation.
            # Inserting with asset_id as position_id creates duplicate NULL-stop records
            # that trip the circuit breaker. Only update price/qty for existing positions.
            try:
                # GOVERNANCE: this is the twice-daily Phase 9 path and previously
                # overwrote quantity from Alpaca unconditionally with zero comparison to
                # the prior DB value - unlike reconciliation.py::check_partial_fills, which
                # runs less often but does alert on a quantity mismatch. A silent quantity
                # drift here (partial fill, missed fill, manual Alpaca-side change) would
                # never surface. Compare first and notify on real drift, same as
                # check_partial_fills.
                cur.execute(
                    "SELECT quantity FROM algo_positions WHERE symbol = %s AND status = 'open'",
                    (symbol,),
                )
                existing_row = cur.fetchone()
                prior_qty = float(existing_row[0]) if existing_row and existing_row[0] is not None else None

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
                        # BUG FOUND 2026-08-16: same falsy-vs-None anti-pattern as above -
                        # current_price=0.0 or position_value=0.0 are legitimate values, not
                        # "missing", and must not be silently written as NULL.
                        float(current_price) if current_price is not None else None,
                        float(position_value) if position_value is not None else None,
                        symbol,
                    ),
                )
                if cur.rowcount > 0:
                    synced_count += 1
                    # CRITICAL FIX: this compared int(prior_qty) != int(qty_float) - this system
                    # actively trades fractional shares (order_manager.py), so a genuine
                    # sub-1-share drift (e.g. DB=10.9, Alpaca=10.1 - a real ~0.8-share, up to
                    # hundreds of dollars depending on price, correction from a partial fill or
                    # manual adjustment) truncated to int(10.9)=10 == int(10.1)=10 and was
                    # silently treated as "no drift" - no warning logged, no notify() alert. The
                    # DB quantity was still correctly overwritten to match the broker either way
                    # (the UPDATE above runs unconditionally), so this never caused a wrong final
                    # state - only a missed operator alert for exactly the sub-1-share drift this
                    # check exists to catch. Compare with a small tolerance for float precision
                    # instead of truncating.
                    if prior_qty is not None and abs(prior_qty - qty_float) > 1e-6:
                        logger.warning(
                            f"[POSITION_SYNC] Quantity drift for {symbol}: DB had {prior_qty}, "
                            f"Alpaca reports {qty_float} - overwriting DB to match broker (source of truth)."
                        )
                        try:
                            from algo.reporting import notify

                            notify(
                                severity="warning",
                                title="Phase 9 Position Quantity Drift",
                                message=(f"{symbol}: qty corrected from {prior_qty} to {qty_float} to match Alpaca"),
                                symbol=symbol,
                                details={"symbol": symbol, "db_quantity": prior_qty, "alpaca_quantity": qty_float},
                            )
                        except (ValueError, TypeError, RuntimeError) as notify_err:
                            logger.error(f"Failed to send position drift notification for {symbol}: {notify_err}")
                else:
                    logger.warning(
                        f"[POSITION_SYNC] No existing open position for {symbol} - skipping (not algo-tracked)"
                    )
            except Exception as e:
                logger.error(f"[POSITION_SYNC] Failed to update position {symbol}: {e}")
                raise RuntimeError(f"[POSITION_SYNC] Database error updating position {symbol}: {e}") from e

        # CRITICAL FIX: Do NOT automatically close positions not found at Alpaca.
        # The old behavior was:
        #   - If a position exists in DB but not in Alpaca → automatically close it
        # This caused mass closures when:
        #   - Order fill confirmation was still pending (position not yet at broker)
        #   - Alpaca API lag/timeouts returned incomplete position list
        #   - Network issues between broker sync and position creation
        #
        # New behavior: Audit and alert instead of silently closing
        # Positions should only be closed when we have proof they were actually closed:
        # - Alpaca explicitly returned a closed position
        # - Exit order was confirmed filled
        # - NOT just because Alpaca didn't list it (could be sync lag)

        try:
            cur.execute(
                """
                SELECT DISTINCT symbol FROM algo_positions
                WHERE status = 'open' AND symbol != ALL(%s)
            """,
                (list(alpaca_symbols),),
            )
            missing_positions = [row[0] for row in cur.fetchall()]

            if missing_positions:
                # ALERT but do NOT close - log for manual operator review
                logger.warning(
                    f"[POSITION_SYNC] ALERT: {len(missing_positions)} positions in DB but not in Alpaca: "
                    f"{', '.join(missing_positions[:10])}{'...' if len(missing_positions) > 10 else ''}. "
                    f"NOT automatically closing - may be fill-pending, API lag, or network sync issue. "
                    f"Manual review required if these should actually be closed."
                )
                try:
                    from algo.reporting import notify

                    notify(
                        severity="warning",
                        title="Position Sync Alert - Missing at Broker",
                        message=f"{len(missing_positions)} positions in DB but not found at Alpaca. "
                        f"May indicate fill-pending orders or broker sync lag. "
                        f"Review: {', '.join(missing_positions[:5])}{'...' if len(missing_positions) > 5 else ''}",
                        details={"missing_positions": missing_positions},
                    )
                except Exception as notify_err:
                    logger.error(f"[POSITION_SYNC] Failed to send alert: {notify_err}")

            closed_count = 0  # No longer auto-closing, only alerting

        except Exception as e:
            logger.error(f"[POSITION_SYNC] Failed to audit missing positions: {e}")
            raise RuntimeError(f"[POSITION_SYNC] Database error auditing positions: {e}") from e

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
        untracked_count, untracked_closed_count = self._sync_untracked_positions(cur, orphan_symbols, alpaca_positions)

        return {
            "message": f"Synced {synced_count} algo positions, marked {closed_count} as closed. "
            f"Tracked {untracked_count} untracked positions.",
            "orphan_symbols": orphan_symbols,
            "synced_count": synced_count,
            "closed_count": closed_count,
            "untracked_count": untracked_count,
            "untracked_closed_count": untracked_closed_count,
        }
