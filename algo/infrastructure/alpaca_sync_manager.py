#!/usr/bin/env python3
"""Alpaca account synchronization and position management.

Extracted from DailyReconciliation to reduce monolithic design and enable
independent testing of position sync logic.
"""

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from algo.config.credential_manager import get_algo_owner_cognito_sub, get_credential_manager
from algo.trading.executor_strategies import create_execution_mode_strategy
from utils.db.advisory_locks import ALGO_POSITIONS_LOCK_ID, acquire_advisory_lock, release_advisory_lock

logger = logging.getLogger(__name__)

# A position missing at Alpaca for more than this long has had many reconciliation cycles
# (the orchestrator runs multiple passes/day) to resolve a genuine fill-pending/API-lag
# condition on its own - continued absence past this window is a real, persistent divergence,
# not transient sync noise. See _find_stale_missing_symbols's docstring.
STALE_MISSING_ESCALATION_HOURS = 24

# An open (resting/unfilled) Alpaca order with no matching algo_trades row younger than this
# is treated as a genuine crash-orphan, not an in-flight transaction still mid-commit - see
# find_orphaned_open_orders's docstring.
ORPHANED_ORDER_GRACE_MINUTES = 10


def _find_stale_missing_symbols(missing_rows: list[tuple[str, Any]]) -> list[str]:
    """Of the symbols found "in DB but not at Alpaca" this cycle, return the ones that have
    been missing for more than STALE_MISSING_ESCALATION_HOURS - see the FIXED 2026-09-07
    comment at this function's call site in _sync_alpaca_positions_impl for the full
    rationale. Split out of that function (same C901-complexity-budget reason as
    _cancel_stale_orders_for_missing_positions below) rather than inlined.

    algo_positions.updated_at is the only signal ever written for an open position by the
    matched-position branch of _sync_alpaca_positions_impl - a row still missing this cycle
    keeps whatever updated_at it had from its last successful match, so its staleness is a
    direct, real measurement of how long the divergence has actually persisted.
    """
    stale_missing = []
    for symbol, updated_at in missing_rows:
        if updated_at is None:
            continue
        # algo_positions.updated_at is written via SQL CURRENT_TIMESTAMP - a naive value here
        # is in the DB session's local wall-clock timezone, not UTC (same documented
        # convention as position_order_management.py's stale-order age check; see
        # get_db_timezone()'s docstring). Mislabeling it as UTC would silently shift the
        # staleness window by the DB session's UTC offset.
        if updated_at.tzinfo is None:
            from utils.db.timezone_utils import get_db_timezone

            updated_at = updated_at.replace(tzinfo=get_db_timezone())
        age_hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
        if age_hours > STALE_MISSING_ESCALATION_HOURS:
            stale_missing.append(symbol)
    return stale_missing


def _is_non_finite_qty(symbol: str, raw_qty: Any, qty_float: float) -> bool:
    """True if qty_float is NaN/Infinity - caller must skip this position rather than
    write a non-finite quantity (see the 2026-09-01 BUG FOUND comment at each call site)."""
    if not math.isfinite(qty_float):
        logger.critical(
            f"[POSITION_SYNC] {symbol}: Alpaca returned non-finite qty={raw_qty!r} - "
            "skipping this position rather than writing a NaN/Infinity quantity."
        )
        return True
    return False


def _finite_price_or_none(symbol: str, raw_price: Any) -> float | None:
    """Converts raw_price to float, returning None (not a NaN/Infinity float) if it's
    missing or non-finite - see the 2026-09-01 BUG FOUND comment at each call site."""
    if raw_price is None:
        return None
    price_float = float(raw_price)
    if not math.isfinite(price_float):
        logger.critical(
            f"[POSITION_SYNC] {symbol}: Alpaca returned non-finite current_price={raw_price!r} - "
            "treating as unavailable rather than writing NaN/Infinity."
        )
        return None
    return price_float


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

    def find_orphaned_open_orders(self, cur: Any) -> list[dict[str, Any]]:
        """Find open (resting, unfilled) Alpaca orders with no matching algo_trades row.

        REAL-MONEY-READINESS FINDING (2026-09-10, order-execution re-audit): the crash-
        recovery story for order submission has a gap this method closes. executor.py's
        _with_cursor wraps the broker POST /v2/orders call and the algo_trades INSERT in a
        single DB transaction (see executor.py's _execute_entry_txn/_with_cursor) - if the
        process dies after Alpaca accepts the order but before that transaction commits, the
        INSERT rolls back entirely. sync_alpaca_positions (above) only catches this once the
        order FILLS into a real position (orphan_symbols cross-check against algo_positions).
        An order that is still resting/unfilled (status new/accepted/partially_filled) at the
        moment of the crash is invisible to both algo_trades (rolled back) and
        sync_alpaca_positions (no position exists yet) - it would sit unrecorded until it
        either fills (becoming an algo_untracked_positions row, once discovered) or expires,
        with nothing in between ever surfacing it.

        client_order_id doubles as the idempotency_key we insert into algo_trades (see
        executor.py's send_bracket_order call site: "use idempotency_key ... NOT trade_id" -
        same 64-char SHA256 hexdigest on both sides), so a straightforward existence check is
        enough to detect the gap - no separate order-tracking table needed.

        Excludes orders submitted within ORPHANED_ORDER_GRACE_MINUTES of "now" - a genuinely
        in-flight transaction (broker accepted, DB commit not yet reached) is not evidence of
        a crash, and this reconciliation pass runs far more often than any single entry
        transaction should ever take to complete.

        FIXED 2026-09-10 (check_silent_fallbacks pre-commit hook): raises instead of silently
        returning [] when credentials are missing - a caller reaching this method without
        Alpaca credentials configured is a real misuse (the sole real caller,
        phase9_reconciliation.py's _reconcile_open_orders_step, already checks
        sync_mgr.alpaca_key/alpaca_secret itself and skips with an explicit log BEFORE ever
        calling this method), and a silent [] here would be indistinguishable from "checked
        and found no orphans" - the exact silent-fallback shape GOVERNANCE.md flags, same
        fail-loud discipline as the timeout/fetch-failure branches below.
        """
        if not self._alpaca_key or not self._alpaca_secret:
            raise RuntimeError(
                "[ORDER_RECONCILE] find_orphaned_open_orders called with no Alpaca credentials "
                "configured - callers must check alpaca_key/alpaca_secret before calling."
            )

        try:
            url = f"{self._alpaca_base_url}/v2/orders"
            headers = {
                "APCA-API-KEY-ID": self._alpaca_key,
                "APCA-API-SECRET-KEY": self._alpaca_secret,
                "Accept": "application/json",
            }
            timeout = self.config.get("api_request_timeout_seconds")
            if timeout is None:
                raise ValueError(
                    "CRITICAL: api_request_timeout_seconds config missing. "
                    "API requests require explicit timeout configuration. "
                    "Check config and ensure api_request_timeout_seconds is set."
                )
            response = self._session.get(
                url, headers=headers, params={"status": "open", "limit": "500"}, timeout=timeout
            )
            response.raise_for_status()
            open_orders = response.json()
        except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
            logger.error(f"[ORDER_RECONCILE] Failed to fetch open Alpaca orders: {e}")
            raise RuntimeError(f"[ORDER_RECONCILE] Cannot fetch open orders from Alpaca: {e}") from e

        if not open_orders:
            return []

        client_order_ids = [o.get("client_order_id") for o in open_orders if o.get("client_order_id")]
        if not client_order_ids:
            return []

        cur.execute(
            "SELECT idempotency_key FROM algo_trades WHERE idempotency_key = ANY(%s)",
            (client_order_ids,),
        )
        known_ids = {row[0] for row in cur.fetchall()}

        grace_cutoff = datetime.now(timezone.utc).timestamp() - (ORPHANED_ORDER_GRACE_MINUTES * 60)
        orphans = []
        for order in open_orders:
            client_order_id = order.get("client_order_id")
            if not client_order_id or client_order_id in known_ids:
                continue
            submitted_at = order.get("submitted_at") or order.get("created_at")
            if submitted_at:
                try:
                    submitted_ts = datetime.fromisoformat(str(submitted_at).replace("Z", "+00:00")).timestamp()
                    if submitted_ts > grace_cutoff:
                        continue
                except ValueError:
                    pass  # Unparseable timestamp - don't let it hide a genuine orphan; treat as orphaned.
            orphans.append(order)
        return orphans

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
                # BUG FOUND 2026-09-01 (real-money-readiness pass): same non-finite gap as
                # _reconcile_positions's main sync loop below (see its own comment) - qty/
                # current_price from Alpaca were never checked for NaN/Infinity before being
                # written to algo_untracked_positions.
                if _is_non_finite_qty(symbol, pos_data["qty"], qty_float):
                    continue
                current_price = _finite_price_or_none(symbol, pos_data["current_price"])
                if current_price is None:
                    continue
                position_value = qty_float * current_price

                try:
                    cur.execute(
                        "SELECT id, protective_stop_order_id FROM algo_untracked_positions WHERE symbol = %s LIMIT 1",
                        (symbol,),
                    )
                    existing = cur.fetchone()
                    existing_stop_order_id = existing[1] if existing and len(existing) > 1 else None

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

                # REAL-MONEY-READINESS FIX (2026-09-07 audit): attach a standalone broker-side
                # protective stop to any orphaned position that doesn't already have one -
                # best-effort, never raises (a submission failure must not abort the rest of
                # reconciliation; the "Untracked Broker Position(s) Detected" alert above/below
                # already covers the human-notification obligation for this gap either way).
                self._attach_protective_stop_if_missing(cur, symbol, qty_float, current_price, existing_stop_order_id)

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
            # BUG FOUND 2026-09-07 (real-money-readiness audit): this used to be an UPDATE
            # that only bumped `updated_at` for rows whose symbol is no longer in the current
            # orphan_symbols list - it never actually removed or flagged them. Every consumer
            # of this table (lambda/api/routes/algo_handlers/dashboard/positions.py's
            # untracked-position count/list, both grepped repo-wide) reads it with NO
            # last_seen_at/staleness filter at all, so a row created once - a manual broker
            # position later closed at Alpaca, or one that became properly algo-tracked -
            # stayed in "Untracked Broker Position(s)" counts/alerts forever. For a real-money
            # dashboard, a permanently-stuck phantom alert is exactly the kind of noise that
            # trains an operator to stop trusting (or stop reading) the one alert meant to
            # catch a genuinely orphaned, un-stopped position. Migration 1118's own column
            # comment says last_seen_at is "used to detect closed positions" - actually do
            # that here by deleting rows for symbols no longer orphaned this cycle, rather
            # than leaving that intent unimplemented. Safe when orphan_symbols is empty too:
            # `symbol != ALL('{}')` is true for every row, correctly clearing the table when
            # Alpaca currently holds zero untracked positions.
            cur.execute(
                """
                DELETE FROM algo_untracked_positions
                WHERE symbol != ALL(%s)
            """,
                (list(orphan_symbols),),
            )
            untracked_closed_count = cur.rowcount
        except Exception as e:
            raise RuntimeError(
                f"[POSITION_SYNC] Failed to remove resolved untracked positions: {e}. "
                f"Cannot clear stale untracked-position rows - position tracking state would be incomplete. "
                f"Reconciliation integrity requires all position updates to succeed."
            ) from e

        if untracked_count > 0 or untracked_closed_count > 0:
            logger.info(
                f"[POSITION_SYNC] Synced {untracked_count} untracked positions, "
                f"marked {untracked_closed_count} as stale"
            )

        return untracked_count, untracked_closed_count

    def _attach_protective_stop_if_missing(
        self,
        cur: Any,
        symbol: str,
        qty: float,
        current_price: float | None,
        existing_stop_order_id: str | None,
    ) -> None:
        """Best-effort: submit a standalone (non-bracket) protective sell-stop for an
        orphaned broker position that doesn't already have one live. Real-money-readiness
        fix (2026-09-07 audit) - see the comment at this method's call site for the full
        rationale (algo_untracked_positions is deliberately kept out of algo_positions, so
        this attaches downside protection without enrolling the position in algo-managed
        signal-driven exits).

        Never raises: a failure here must not abort the rest of untracked-position sync or
        the reconciliation run - the existing "Untracked Broker Position(s) Detected"
        critical alert already covers the human-notification obligation for this gap.
        """
        try:
            enabled = self.config.get("untracked_position_auto_protective_stop_enabled")
            if enabled is None:
                enabled = True  # fail toward protecting capital, not toward silently skipping it
            if not enabled:
                return

            if not (self.alpaca_key and self.alpaca_secret and self.alpaca_base_url):
                logger.warning(
                    f"[UNTRACKED_STOP] {symbol}: Alpaca credentials/base URL not configured - "
                    "skipping protective stop submission."
                )
                return

            # REAL-MONEY-READINESS FIX (2026-09-10 order-execution re-audit): mirrors
            # phase9_reconciliation.py's _verify_open_position_stop_loss_protection_step
            # explicit execution_mode guard (2026-09-07). This method runs on every
            # sync_alpaca_positions cycle in every execution mode and, before this fix, only
            # gated on credential presence - relying entirely on self.alpaca_base_url having
            # already been resolved to the paper endpoint for non-"auto" modes by
            # AlpacaSyncManager.__init__'s create_execution_mode_strategy(...) call. That's an
            # implicit coupling, not a guard at this call site: a future refactor of that
            # shared resolution logic could silently start submitting real protective-stop
            # orders here with nothing catching it. Fail closed instead of trusting it.
            execution_mode = str(self.config.get("execution_mode") or "").lower()
            base_url_is_paper = "paper" in self.alpaca_base_url.lower()
            if execution_mode != "auto" and not base_url_is_paper:
                logger.critical(
                    f"[UNTRACKED_STOP] {symbol}: protective stop submission ABORTED - "
                    f"execution_mode='{execution_mode}' but resolved Alpaca base_url does not "
                    f"look like the paper endpoint ({self.alpaca_base_url}). Refusing to submit "
                    "orders in a non-auto mode against what may be a live endpoint."
                )
                return

            from algo.trading.order_manager import OrderManager

            order_mgr = OrderManager(self.alpaca_key, self.alpaca_secret, self.alpaca_base_url)

            if existing_stop_order_id:
                try:
                    still_live = order_mgr.is_order_still_live(existing_stop_order_id)
                except Exception as e:
                    logger.warning(
                        f"[UNTRACKED_STOP] {symbol}: could not verify existing protective stop "
                        f"{existing_stop_order_id} is still live ({e}) - skipping this cycle "
                        "rather than risking a duplicate submission."
                    )
                    return
                if still_live:
                    return
                if still_live is None:
                    # Paper/local mode, or the order id is no longer resolvable - neither
                    # confirms nor rules out protection. Skip rather than guess; a real
                    # broker order id in auto mode always resolves to True/False here.
                    return
                logger.warning(
                    f"[UNTRACKED_STOP] {symbol}: previously-submitted protective stop "
                    f"{existing_stop_order_id} is no longer live (filled/cancelled) - "
                    "attempting to submit a new one."
                )

            if current_price is None or current_price <= 0 or qty <= 0:
                logger.warning(
                    f"[UNTRACKED_STOP] {symbol}: cannot compute a protective stop without a "
                    f"valid current_price/qty (price={current_price}, qty={qty}) - skipping."
                )
                return

            stop_pct = self.config.get("imported_position_default_stop_loss_pct")
            if stop_pct is None:
                logger.warning(
                    "[UNTRACKED_STOP] imported_position_default_stop_loss_pct config missing - "
                    "skipping protective stop submission this cycle."
                )
                return
            stop_price = round(current_price * (1 - float(stop_pct) / 100.0), 4)
            if stop_price <= 0:
                logger.warning(
                    f"[UNTRACKED_STOP] {symbol}: computed stop_price={stop_price} is not positive - skipping."
                )
                return

            import uuid

            client_order_id = (
                f"untracked-stop-{symbol}-{uuid.uuid5(uuid.NAMESPACE_DNS, f'{symbol}-{qty}-{stop_price}')}"
            )
            result = order_mgr.submit_standalone_protective_stop(
                symbol=symbol,
                qty=qty,
                stop_price=stop_price,
                client_order_id=client_order_id,
                pos_id=None,
            )
            if result.get("success"):
                cur.execute(
                    """
                    UPDATE algo_untracked_positions
                    SET protective_stop_order_id = %s,
                        protective_stop_price = %s,
                        protective_stop_submitted_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s
                    """,
                    (result.get("order_id"), stop_price, symbol),
                )
                logger.critical(
                    f"[UNTRACKED_STOP] {symbol}: attached protective stop @ ${stop_price:.4f} "
                    f"({qty} shares, order id {result.get('order_id')}): {result.get('message')}"
                )
            else:
                logger.critical(
                    f"[UNTRACKED_STOP] {symbol}: FAILED to attach protective stop - this "
                    f"position remains unprotected: {result.get('message')}"
                )
        except Exception as e:
            logger.critical(
                f"[UNTRACKED_STOP] {symbol}: unexpected error attaching protective stop "
                f"(position remains unprotected): {e}",
                exc_info=True,
            )

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
            # BUG FOUND 2026-09-01 (real-money-readiness pass): `qty_float <= 0` is a no-op
            # for NaN (every comparison against NaN is False in Python/IEEE 754), so a
            # malformed Alpaca response (network/proxy corruption, or a numeric string like
            # "nan"/"inf" that float() silently accepts) would fall through this guard and
            # write a non-finite quantity straight into algo_positions.quantity - PostgreSQL
            # NUMERIC legally accepts NaN, so this would persist silently with no exception
            # and no downstream validation catching it. Same NaN/Infinity guard convention
            # this codebase applies everywhere else price-derived data crosses a trust
            # boundary (see e.g. capital_routing.py's math.isnan/isinf checks).
            if _is_non_finite_qty(symbol, qty, qty_float):
                continue
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
            # BUG FOUND 2026-09-01: same non-finite gap as qty_float above - a non-finite
            # current_price would otherwise flow straight into position_value and
            # algo_positions.current_price with no guard.
            current_price_float = _finite_price_or_none(symbol, current_price)
            position_value = qty_float * current_price_float if current_price_float is not None else None

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
                        # "missing", and must not be silently written as NULL. Reuses
                        # current_price_float (already NaN/Infinity-guarded above) rather
                        # than re-converting the raw current_price value here.
                        current_price_float,
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
            # FIXED 2026-09-07 (real-money-readiness audit): also fetch each missing symbol's
            # updated_at, which the matched-position branch above (lines ~639/681) is the ONLY
            # thing that ever bumps for an open position - a row excluded from that branch (i.e.
            # still missing at Alpaca this cycle) keeps whatever updated_at it had from its last
            # successful match. That makes staleness of updated_at a direct, real measurement of
            # "how long has this position actually been missing," not just "missing this one
            # check." Before this fix, every cycle re-alerted at the SAME "warning" severity
            # forever with no escalation - a position genuinely closed outside the algo (a stop
            # filled with nobody watching) could sit "open" in the DB indefinitely as long as the
            # recurring warning kept getting missed, with no automatic path to operator attention
            # rising to match how stale the divergence actually is.
            cur.execute(
                """
                SELECT symbol, updated_at FROM algo_positions
                WHERE status = 'open' AND symbol != ALL(%s)
            """,
                (list(alpaca_symbols),),
            )
            missing_rows = cur.fetchall()
            missing_positions = [row[0] for row in missing_rows]

            if missing_positions:
                stale_missing = _find_stale_missing_symbols(missing_rows)
                escalate = bool(stale_missing)

                # ALERT but do NOT close - log for manual operator review
                logger.warning(
                    f"[POSITION_SYNC] ALERT: {len(missing_positions)} positions in DB but not in Alpaca: "
                    f"{', '.join(missing_positions[:10])}{'...' if len(missing_positions) > 10 else ''}. "
                    f"NOT automatically closing - may be fill-pending, API lag, or network sync issue. "
                    f"Manual review required if these should actually be closed."
                    + (
                        f" ESCALATED: {len(stale_missing)} of these have been missing for over "
                        f"{STALE_MISSING_ESCALATION_HOURS}h - this is no longer transient sync lag."
                        if escalate
                        else ""
                    )
                )
                try:
                    from algo.reporting import notify

                    notify(
                        severity="critical" if escalate else "warning",
                        title=(
                            "Position Sync CRITICAL - Persistently Missing at Broker"
                            if escalate
                            else "Position Sync Alert - Missing at Broker"
                        ),
                        message=f"{len(missing_positions)} positions in DB but not found at Alpaca. "
                        f"May indicate fill-pending orders or broker sync lag. "
                        f"Review: {', '.join(missing_positions[:5])}{'...' if len(missing_positions) > 5 else ''}"
                        + (
                            f" {len(stale_missing)} have been missing for over "
                            f"{STALE_MISSING_ESCALATION_HOURS}h: {', '.join(stale_missing[:5])} - "
                            f"treat as confirmed-closed pending manual verification, not sync lag."
                            if escalate
                            else ""
                        ),
                        details={"missing_positions": missing_positions, "stale_missing": stale_missing},
                    )
                except Exception as notify_err:
                    logger.error(f"[POSITION_SYNC] Failed to send alert: {notify_err}")

                # ORPHANED BRACKET LEG FIX (2026-09-06, real-money-readiness dig): a position
                # closed entirely outside the algo (manual close via Alpaca's own dashboard/
                # API, or any other out-of-band exit) never runs executor_exit_handler.py's
                # normal cancel-sibling-legs step. The bracket's stop-loss/take-profit leg(s)
                # are then left resting live at the broker for a symbol the account no longer
                # holds - harmless today (a long-only account can't fill a sell against zero
                # shares), but if the algo re-enters this exact symbol later, that stale,
                # DB-unlinked order can fire against the NEW position without the algo ever
                # knowing it exists. Cancelling here is a pure risk-reduction action (removes
                # a stale order, never touches algo_positions/algo_trades) - it does NOT
                # change the deliberate alert-and-manually-review decision above about the
                # DB-side "should this be marked closed" question, which stays untouched.
                # Split into its own function (not inlined here) to keep
                # _sync_alpaca_positions_impl's own cyclomatic complexity under the repo's
                # C901 limit.
                self._cancel_stale_orders_for_missing_positions(missing_positions)

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

    def _cancel_stale_orders_for_missing_positions(self, missing_positions: list[str]) -> None:
        """Cancel any resting broker orders for symbols confirmed closed at Alpaca but still
        marked 'open' in algo_positions - see the ORPHANED BRACKET LEG FIX comment at this
        method's call site in _sync_alpaca_positions_impl for the full rationale. Split out
        of that function to keep its own cyclomatic complexity under the repo's C901 limit.
        """
        if not (self.alpaca_key and self.alpaca_secret and self.alpaca_base_url):
            return

        from algo.trading.order_manager import OrderManager

        cleanup_order_mgr = OrderManager(self.alpaca_key, self.alpaca_secret, self.alpaca_base_url)
        for missing_symbol in missing_positions:
            try:
                cleanup_result = cleanup_order_mgr.cancel_all_open_orders_for_symbol(missing_symbol)
                if cleanup_result.get("cancelled_order_ids"):
                    logger.warning(f"[POSITION_SYNC] {missing_symbol}: {cleanup_result.get('message')}")
                elif not cleanup_result.get("success"):
                    logger.error(
                        f"[POSITION_SYNC] {missing_symbol}: stale-order cleanup failed - "
                        f"{cleanup_result.get('message')}"
                    )
            except Exception as cleanup_err:
                logger.error(
                    f"[POSITION_SYNC] {missing_symbol}: stale-order cleanup raised unexpectedly: {cleanup_err}",
                    exc_info=True,
                )
