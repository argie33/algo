"""Stale-order detection/cancellation methods for PositionMonitor, extracted from
algo/monitoring/position_monitor.py (2026-09-05, file-size ratchet: that file is a Tier-2
bloater flagged for decomposition, same pattern already used for
`algo/monitoring/position_corporate_actions.py`'s CorporateActionsMixin). Bodies are
verbatim, no logic changed - mixed into PositionMonitor, which still defines the `config`
instance attribute these methods read via `self`.

`DatabaseContext`/`requests`/`time`/`get_alpaca_credentials`/`get_alpaca_base_url` are
accessed via the position_monitor module object at call time (not imported by name here)
because existing tests patch `algo.monitoring.position_monitor.DatabaseContext`/`.requests`/
`.time`/`.get_alpaca_credentials`/`.get_alpaca_base_url` expecting that to affect these
methods - a plain import here would silently stop seeing those patches (same reasoning as
position_corporate_actions.py). `algo.monitoring.position_monitor` itself imports this module
at load time, so the reference is resolved lazily (inside the method bodies, not at import
time) to avoid a circular-import failure.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

import psycopg2

import algo.monitoring.position_monitor as _pm

logger = logging.getLogger(__name__)


class PositionOrderManagementMixin:
    """Stale pending-order detection and Alpaca cancellation methods for PositionMonitor.
    Not usable standalone - relies on the `config` instance attribute defined on
    PositionMonitor itself.
    """

    config: Any

    def check_stale_orders(self, current_date: _date | None = None) -> dict[str, Any]:
        """Check for orders stuck in pending state >1 hour. Auto-cancel if >2 hours.

        Stuck orders = likely API issue or rejection. Orders >2 hours old are auto-cancelled
        (fail-closed: stuck orders block exit logic, so cancellation is safer than waiting).
        Filters out orders for halted symbols (these stay pending naturally).

        Returns dict with:
          - status: "OK", "STALE_ORDERS_FOUND", "AUTO_CANCELLED", or "ERROR"
          - count: number of orders in that state
          - orders: list of order tuples
          - cancelled: list of cancelled order details (if auto_cancelled)
        """
        if current_date is None:
            current_date = _date.today()

        try:
            alert_threshold = int(self.config["stale_order_alert_minutes"])
            auto_cancel_threshold = int(self.config["stale_order_auto_cancel_minutes"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

        with _pm.DatabaseContext("write") as cur:  # type: ignore[attr-defined]
            try:
                cur.execute(
                    """
                    SELECT trade_id, symbol, entry_price, entry_quantity, created_at
                    FROM algo_trades
                    WHERE status = 'pending'
                      AND created_at < CURRENT_TIMESTAMP - INTERVAL %s
                    ORDER BY created_at ASC
                """,
                    (f"{alert_threshold} minutes",),
                )
                stale_orders = cur.fetchall()
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"Failed to check for stale orders: {e}. Cannot proceed without this critical check."
                ) from e

            if stale_orders:
                # Filter out halted symbols (halts are normal, not actionable)
                # Check Alpaca API for symbol halts
                try:
                    from algo.infrastructure import MarketEventHandler

                    meh = MarketEventHandler(self.config)
                    filtered_stale = []
                    halted_orders = []
                    for row in stale_orders:
                        trade_id, symbol, price, qty, created_at = row

                        # Check Alpaca API for halt status
                        alpaca_halt = False
                        try:
                            halt_check = meh.check_single_stock_halt(symbol)
                            if halt_check and halt_check.get("error"):
                                raise RuntimeError(
                                    f"Halt check failed for {symbol}: {halt_check.get('reason', halt_check['error'])}. "
                                    f"Cannot proceed without knowing which orders are halted."
                                )
                            if halt_check and halt_check.get("halted"):
                                alpaca_halt = True
                        except TimeoutError:
                            logger.warning(
                                f"[HALT_CHECK] Alpaca halt check timed out for {symbol} (2s timeout). "
                                f"Treating as not halted."
                            )
                            alpaca_halt = False

                        # If halted, mark as halted and skip
                        if alpaca_halt:
                            logger.info(f"    {trade_id} {symbol} pending (but halted, expected)")
                            halted_orders.append(row)
                            logger.critical(f"[HALT_CHECK] Symbol {symbol} is HALTED (Alpaca API)")
                            continue
                        filtered_stale.append(row)
                    stale_orders = filtered_stale
                except (ValueError, ZeroDivisionError, TypeError) as e:
                    logger.critical(
                        f"[HALT_CHECK] Could not check halts for stale orders: {e}. "
                        f"Continuing without halt filtering will process halted orders."
                    )
                    raise RuntimeError(
                        f"Halt check failed: {e}. Cannot proceed without knowing which orders are halted."
                    ) from e

                if stale_orders:
                    logger.info(
                        f"\n  [ALERT] Found {len(stale_orders)} orders pending >{alert_threshold}m (excluding halted):"
                    )

                    cancelled_orders = []
                    trades_to_update = []
                    audit_entries = []

                    for row in stale_orders:
                        trade_id, symbol, price, qty, created_at = row
                        # algo_trades.created_at is a `timestamp without time zone` column
                        # written via SQL CURRENT_TIMESTAMP, so a naive value here is in the
                        # DB session's local wall-clock timezone (utils/bulk_insert_manager.py's
                        # documented convention), not UTC - confirmed live this session's actual
                        # `SHOW timezone` is America/Chicago, 5+ hours off UTC. Mislabeling it as
                        # UTC via .replace(tzinfo=timezone.utc) silently inflated age_minutes by
                        # that offset - a pending order submitted minutes ago would compute as
                        # hours old, immediately tripping alert_threshold/auto_cancel_threshold
                        # and cancelling a legitimate, still-processing live order. Same bug class
                        # already fixed in algo/risk/market_exposure.py's cache-age check and
                        # algo/trading/pretrade_checks.py's re-entry cooldown: resolve the real
                        # session timezone dynamically instead of assuming UTC.
                        if not getattr(created_at, "tzinfo", None):
                            from utils.db.timezone_utils import get_db_timezone

                            naive_tz = get_db_timezone()
                            created_at = created_at.replace(tzinfo=naive_tz)
                        age_minutes = int((datetime.now(timezone.utc) - created_at).total_seconds() / 60)
                        logger.info(f"    {trade_id} {symbol} {qty}@{price} (pending {age_minutes}m)")

                        # Auto-cancel if > 2 hours (or configured threshold)
                        if age_minutes >= auto_cancel_threshold:
                            # Fail fast on Alpaca cancellation - don't mark DB as cancelled if API call fails
                            try:
                                self._cancel_on_alpaca(trade_id)
                            except (ValueError, ZeroDivisionError, TypeError) as api_e:
                                logger.critical(
                                    f"[STALE_ORDER] Could not cancel {trade_id} on Alpaca: {api_e}. "
                                    f"Alpaca and database will diverge if we mark cancelled in DB. Aborting auto-cancel."
                                )
                                raise RuntimeError(
                                    f"Alpaca cancellation failed for {trade_id}: {api_e}. "
                                    f"Cannot proceed with DB update to avoid state divergence."
                                ) from api_e

                            # Only mark as cancelled after successful Alpaca cancellation
                            trades_to_update.append(trade_id)
                            audit_entries.append(
                                (
                                    "STALE_ORDER_AUTO_CANCELLED",
                                    symbol,
                                    f"Trade {trade_id}: {qty}@${price} pending {age_minutes}m >= auto-cancel threshold",
                                    "WARN",
                                    "position_monitor",
                                    "auto_cancelled",
                                )
                            )
                            cancelled_orders.append(
                                {
                                    "trade_id": trade_id,
                                    "symbol": symbol,
                                    "qty": qty,
                                    "price": price,
                                    "age_minutes": age_minutes,
                                }
                            )
                            logger.warning(
                                f"  [AUTO-CANCEL] {trade_id} {symbol} (pending {age_minutes}m >= {auto_cancel_threshold}m threshold)"
                            )

                    # Batch update database (atomic: trades + audit logs via savepoint)
                    if trades_to_update:
                        sp_name = "sp_stale_cancel"
                        cur.execute(f"SAVEPOINT {sp_name}")
                        try:
                            cur.execute(
                                """UPDATE algo_trades
                                   SET status = %s, updated_at = CURRENT_TIMESTAMP
                                   WHERE trade_id = ANY(%s)""",
                                ("cancelled", trades_to_update),
                            )
                            cur.executemany(
                                """INSERT INTO algo_audit_log (
                                       action_type, symbol, action_date, details, severity, actor, status, created_at
                                   ) VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, CURRENT_TIMESTAMP)""",
                                audit_entries,
                            )
                        except (
                            psycopg2.DatabaseError,
                            psycopg2.OperationalError,
                        ) as audit_e:
                            try:
                                cur.execute(f"ROLLBACK TO {sp_name}")
                            except (
                                psycopg2.DatabaseError,
                                psycopg2.OperationalError,
                                psycopg2.ProgrammingError,
                            ) as rb_err:
                                logger.error(
                                    f"[AUDIT_FAILURE] Savepoint rollback failed: {rb_err} (transaction may be aborted)"
                                )
                            logger.critical(
                                f"[AUDIT_FAILURE] Stale order batch transaction failed (rolled back): {audit_e}"
                            )
                            raise

                    # Proceed to return (outer transaction will commit)
                    if cancelled_orders:
                        return {
                            "status": "AUTO_CANCELLED",
                            "count": len(cancelled_orders),
                            "cancelled": cancelled_orders,
                            "alert_count": len(stale_orders) - len(cancelled_orders),
                        }

                    return {
                        "status": "STALE_ORDERS_FOUND",
                        "count": len(stale_orders),
                        "orders": stale_orders,
                    }
            return {"status": "OK", "count": 0}

    def _cancel_on_alpaca(self, trade_id: str) -> None:
        """Cancel a stale pending order on Alpaca API only.

        Raises:
            RuntimeError: If cancellation cannot be verified (fail-fast to prevent state divergence)
        """
        creds = _pm.get_alpaca_credentials()
        base_url = _pm.get_alpaca_base_url(self.config.get("execution_mode"))
        alpaca_key = creds.get("key")
        alpaca_secret = creds.get("secret")

        if not alpaca_key or not alpaca_secret:
            raise RuntimeError(
                f"Cannot cancel stale order {trade_id}: Alpaca credentials unavailable. "
                f"Cannot proceed without ability to verify cancellation at broker."
            )

        url = f"{base_url}/v2/orders/{trade_id}"
        headers = {
            "APCA-API-KEY-ID": alpaca_key,
            "APCA-API-SECRET-KEY": alpaca_secret,
        }
        try:
            timeout = int(self.config["api_request_timeout_seconds"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

        # RETRY (found 2026-07-28, same bug class as order_manager.py's send/cancel fixes):
        # a single-attempt transient 429/503 used to raise RuntimeError immediately, which
        # this function's own caller (line ~169) propagates all the way up as a fail-fast -
        # a brief Alpaca rate-limit hiccup would abort stale-order cleanup for the whole cycle
        # instead of a retryable blip.
        max_attempts = 3
        resp = None
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                resp = _pm.requests.delete(url, headers=headers, timeout=timeout)
            except (_pm.requests.RequestException, _pm.requests.Timeout) as e:
                last_error = e
                logger.warning(
                    f"[STALE_ORDER] {trade_id}: cancel request failed: {e} (attempt {attempt + 1}/{max_attempts})"
                )
                if attempt < max_attempts - 1:
                    _pm.time.sleep(1)
                continue

            if resp.status_code in (429, 503) and attempt < max_attempts - 1:
                wait_time = 2**attempt
                logger.warning(
                    f"[STALE_ORDER] {trade_id}: Alpaca {resp.status_code} - transient, retrying in "
                    f"{wait_time}s (attempt {attempt + 1}/{max_attempts})"
                )
                _pm.time.sleep(wait_time)
                continue
            break

        if resp is None:
            raise RuntimeError(
                f"Failed to cancel stale order {trade_id} on Alpaca: {last_error}. "
                f"Cannot proceed without confirmation of cancellation (DB/broker state would diverge)."
            ) from last_error

        if resp.status_code == 204 or resp.status_code == 200:
            logger.info(f"Successfully cancelled order {trade_id} on Alpaca")
        elif resp.status_code == 404:
            logger.info(f"Order {trade_id} not found on Alpaca (already closed/cancelled)")
        else:
            raise RuntimeError(
                f"Alpaca cancel failed for {trade_id} (unexpected status {resp.status_code}): {resp.text}. "
                f"Cannot mark order as cancelled in DB without broker confirmation."
            )
