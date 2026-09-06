#!/usr/bin/env python3
"""ENTRY-FILL / BROKER-ACCOUNT VALIDATION: partial-fill drift, account fetch, P&L variance

Pure extract-method split of four `DailyReconciliation` methods that validate broker-vs-DB
state outside the exit-price-reconciliation flow (see reconciliation_exit_fills.py for that):

1. `check_partial_fills` - detects and corrects entry-quantity drift between our DB and
   Alpaca's actual filled buy orders (the "Alpaca fills part of an order and then network
   fails before we can sync" case).
2. `_fetch_account` - fetches the broker account dict, with the paper-mode-friendly 401
   fallback used by `run_daily_reconciliation`.
3. `_fetch_initial_capital` - fail-fast fetch of initial capital from broker portfolio
   history (no stale-DB-snapshot fallback), used by the broker-connected cumulative-return
   calculation in reconciliation_broker_snapshot.py.
4. `validate_pnl` - compares broker-reported equity against locally-computed equity within
   tolerance (called by phase9_reconciliation.py).

NO BEHAVIOR CHANGE: every method here is a verbatim relocation of code that used to live
directly on `DailyReconciliation` in reconciliation.py - control flow, thresholds, SQL, and
log messages are unchanged. Comments documenting non-obvious business logic (fix-history
notes, bug-found dates) moved verbatim with the code they describe.

Mixed into DailyReconciliation via multiple inheritance - every `self.` reference here
(self.broker, self.config) resolves normally through the instance regardless of which file
defines the attribute, matching the convention already established by
reconciliation_paper_mode.py / reconciliation_broker_positions.py /
reconciliation_broker_snapshot.py / reconciliation_exit_fills.py.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import psycopg2
import requests
from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure.broker_adapter import BrokerAdapter
from algo.reporting import notify
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)


class FillAndAccountValidationMixin:
    """Mixin providing entry-fill drift detection, broker account/initial-capital fetch,
    and broker-vs-local P&L variance validation."""

    # Attribute set by DailyReconciliation.__init__ - declared here so mypy resolves it on
    # this mixin (same convention as PaperModeReconciliationMixin's `config` annotation).
    broker: BrokerAdapter | None

    def check_partial_fills(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Check for partial fills that haven't been reconciled with Alpaca.

        Detects when orders were only partially filled but the local DB thinks
        they're fully filled. This catches the case when Alpaca fills part of an
        order and then network fails before we can sync.

        Returns: dict with reconciliation status and any detected drift
        """
        try:
            if not self.broker:
                return {"mismatches": 0, "message": "No broker available (paper trading mode)", "no_broker": True}
            orders = self.broker.fetch_closed_orders()
            if not orders:
                logger.debug(
                    "No closed orders returned from broker in partial fill check. "
                    "This is expected if: (1) No orders were placed recently, "
                    "(2) All recent orders are still open/pending. Otherwise, broker API may be unavailable."
                )
                return {"mismatches": 0, "message": "No closed orders to check", "no_orders_available": True}

            # Check each order against our DB records
            mismatches = []
            for order in orders:
                if "symbol" not in order or "filled_qty" not in order or "status" not in order:
                    # CRITICAL: Alpaca API contract violation - cannot reconcile fill status without required fields
                    raise RuntimeError(
                        f"[PARTIAL_FILL_CHECK CRITICAL] Alpaca API returned malformed order (missing required fields). "
                        f"Cannot reconcile fills: {order}. Partial fill detection disabled. "
                        f"API contract violated - check Alpaca API response structure."
                    )
                symbol = order["symbol"]
                # order_manager.send_bracket_order() submits every live entry with
                # client_order_id=idempotency_key (see executor.py's call site) - Alpaca
                # echoes it back on every order object, and algo_trades.idempotency_key is
                # the same deterministic value, so this is the one broker-side field that
                # unambiguously identifies which trade row an order belongs to.
                order_client_order_id = order.get("client_order_id")
                alpaca_filled_qty = float(order["filled_qty"])
                order_status = order["status"]

                if not symbol or alpaca_filled_qty <= 0:
                    continue

                # CRITICAL FIX: fetch_closed_orders() has no side filter (status=[filled,
                # partially_filled] only) - it returns both buy and sell orders. This function
                # exists to catch entry-fill drift (DB entry_quantity vs Alpaca's actual filled
                # buy order), but without a side check, a partial-exit SELL order (T1/T2 partial
                # profit-taking - see executor_exit_handler.py's full_exit=False path) for a
                # still-open trade would match here too, since the trade's status stays in
                # TradeStatus.all_open() until the final leg closes it. Its filled_qty is the
                # (smaller, expected) exit quantity, not the original entry quantity - matching
                # it here would silently shrink entry_quantity to the partial-exit size, and
                # entry_quantity later feeds original_cost_basis/original_risk_dollars for the
                # trade's final pnl_pct/exit_r_multiple in reconcile_exit_fills() (~line 1613,
                # 1713-1722), corrupting reported P&L% and R-multiple for every trade that used a
                # partial exit. reconcile_exit_fills() itself already filters to side == "sell"
                # for the opposite (exit) purpose (~line 1572) - mirror that here for entries.
                if order.get("side") != "buy":
                    continue

                # Find corresponding trade in our DB
                #
                # CRITICAL FIX: this hardcoded list omitted 'pending'/'paper_pending' - exactly
                # the two statuses a trade sits in when "Alpaca fills part of an order and then
                # network fails before we can sync" (this function's own docstring), i.e. the
                # precise desync this check exists to catch. A trade stuck at 'pending' in our
                # DB while Alpaca's own closed-orders feed already shows it filled would never
                # match this WHERE clause, so the mismatch would go undetected. Use
                # TradeStatus.all_open() so every live status is covered.
                open_trade_statuses = TradeStatus.all_open()
                status_placeholders = ", ".join(["%s"] * len(open_trade_statuses))
                # REAL-MONEY-READINESS FIX (2026-09-06): this used to match `WHERE symbol = %s
                # ... ORDER BY trade_date DESC LIMIT 1` with no order-id binding at all - for a
                # pyramided position (2+ open algo_trades rows for the same symbol, a real
                # supported case - see position_sizer.py's own pyramided-position handling),
                # EVERY closed buy order for that symbol in this loop would resolve to the same
                # single "most recent" trade row, since the query result doesn't depend on which
                # order is being checked. An older pyramid leg's own fill-quantity correction
                # would misattribute onto the newer leg's trade_id (or vice versa), corrupting
                # entry_quantity for the wrong trade. Bind to algo_trades.idempotency_key (the
                # same value sent to Alpaca as client_order_id at submission - see
                # order_client_order_id's own comment above) first, since that's unambiguous -
                # one order can only belong to one trade; fall back to the old symbol-only match
                # only when the broker didn't echo a client_order_id (shouldn't happen for an
                # order this system submitted, but keeps this from regressing to "silently
                # skipped" if it ever does) or there's genuinely just one open trade for the
                # symbol.
                db_row = None
                if order_client_order_id:
                    cur.execute(
                        f"""
                        SELECT trade_id, entry_quantity, status
                        FROM algo_trades
                        WHERE idempotency_key = %s AND status IN ({status_placeholders})
                    """,
                        (order_client_order_id, *open_trade_statuses),
                    )
                    db_row = cur.fetchone()

                if db_row is None:
                    cur.execute(
                        f"""
                        SELECT trade_id, entry_quantity, status
                        FROM algo_trades
                        WHERE symbol = %s AND status IN ({status_placeholders})
                        ORDER BY trade_date DESC LIMIT 1
                    """,
                        (symbol, *open_trade_statuses),
                    )
                    db_row = cur.fetchone()

                if db_row is None:
                    continue

                db_trade_id, db_qty, _db_status = db_row

                # Validate quantity data integrity
                if db_qty is None:
                    logger.error(
                        f"[RECONCILIATION] Database quantity NULL for {symbol} (trade_id {db_trade_id}). "
                        f"Cannot reconcile fill without known position size. Manual intervention required."
                    )
                    continue

                # Check for mismatch. CRITICAL FIX: this used to compare int(db_qty) !=
                # int(alpaca_filled_qty), truncating fractional shares before comparing - this
                # system actively trades fractional shares (order_manager.py), so a genuine
                # sub-1-share drift (e.g. db_qty=10.9, alpaca_filled_qty=10.1) truncated to
                # int(10.9)=10 == int(10.1)=10 and was silently classified as "no mismatch".
                # Unlike the equivalent bug already fixed in alpaca_sync_manager.py (where the
                # DB correction ran unconditionally and only the alert was gated), HERE the
                # comparison gates the correction UPDATE itself (see below) - so this
                # truncation didn't just miss an alert, it left algo_trades.entry_quantity
                # silently wrong for any sub-1-share entry-fill drift, with no way for a later
                # reconciliation pass to ever catch it (int(10.9) always equals int(10.1)).
                qty_mismatch = alpaca_filled_qty > 0 and abs(float(db_qty) - alpaca_filled_qty) > 1e-6

                if qty_mismatch:
                    # Quantity drift detected - Alpaca has different fill than DB
                    mismatches.append(
                        {
                            "symbol": symbol,
                            "trade_id": db_trade_id,
                            "db_quantity": float(db_qty),
                            "alpaca_filled": alpaca_filled_qty,
                            "alpaca_status": order_status,
                        }
                    )

                    # Correct the DB quantity to match Alpaca (source of truth). algo_trades.
                    # entry_quantity is numeric(_, 4) - write the precise fractional value, not
                    # the truncated int (which would itself re-introduce the same precision loss
                    # this fix removes from the comparison).
                    cur.execute(
                        "UPDATE algo_trades SET entry_quantity = %s, updated_at = CURRENT_TIMESTAMP WHERE trade_id = %s",
                        (alpaca_filled_qty, db_trade_id),
                    )
                    logger.warning(
                        f"[PARTIAL_FILL] Corrected {symbol} quantity: DB had {db_qty}, Alpaca filled {alpaca_filled_qty}"
                    )

                    try:
                        # strict=True: notify() otherwise swallows every delivery failure
                        # internally and just logs, which made the except clause below
                        # non-functional for its actual purpose (see the comment there) -
                        # it could never see a psycopg2 error notify() had already caught
                        # and discarded itself.
                        notify(
                            severity="warning",
                            title="Partial Fill Detected and Corrected",
                            message=f"{symbol}: Quantity corrected from {db_qty} to {alpaca_filled_qty} to match Alpaca.",
                            symbol=symbol,
                            details={
                                "symbol": symbol,
                                "db_quantity": float(db_qty),
                                "alpaca_filled": alpaca_filled_qty,
                            },
                            strict=True,
                        )
                    except Exception as e:
                        # CRITICAL FIX: this used to re-raise, which propagates out of this
                        # loop, out of the single `with DatabaseContext("write") as cur:`
                        # block that phase4_reconciliation.py opens around the whole
                        # check_partial_fills() call - rolling back the UPDATE just made
                        # above (which corrects a genuinely stale DB quantity to match
                        # Alpaca, the source of truth) AND every other symbol's correction
                        # already applied earlier in this same loop/transaction. A flaky
                        # alert channel would silently discard real, already-verified
                        # data-integrity corrections instead of just failing to announce
                        # them. Same bug class as the entry/exit notification-rollback
                        # fixes (executor_entry_handler.py, executor_exit_handler.py) -
                        # log-and-continue so the correction survives regardless of
                        # whether the operator alert lands.
                        logger.error(
                            f"[PARTIAL_FILL_ALERT] Failed to notify operator of fill correction "
                            f"for {symbol} (non-blocking, correction already applied): {e}"
                        )

            return {
                "checked": len(orders),
                "mismatches": len(mismatches),
                "message": f"Checked {len(orders)} orders; corrected {len(mismatches)} partial fills",
                "details": mismatches,
            }

        except (
            ValueError,
            requests.RequestException,
            json.JSONDecodeError,
            psycopg2.DatabaseError,
        ) as e:
            # Handle Alpaca 401/auth errors: return a structured auth_unavailable=True result
            # rather than raising, so the caller (phase4_reconciliation.py) can distinguish
            # this from a generic reconciliation failure. NOTE (2026-08-10 audit): the
            # `mismatches: 0` here does NOT mean "checked and clean" - phase4_reconciliation.py
            # explicitly documents and enforces this ("The 0 mismatches means 'not checked',
            # not 'checked and clean'") by fail-fasting on `auth_unavailable=True` regardless
            # of the mismatches count (see its own FAIL-FAST block). Also NOTE: __init__ only
            # ever constructs a real `self.broker` when execution_mode == "auto" - this branch
            # can only be reached in that mode (paper/dry/review short-circuit earlier via the
            # `if not self.broker` check above), so despite the "paper mode" wording below,
            # this is exclusively a live-mode signal; the fail-fast caller behavior is what
            # actually keeps this safe, not this comment's description of when it fires.
            error_str = str(e).lower()
            if "401" in str(e) or "unauthorized" in error_str or "alpaca" in error_str:
                logger.warning(
                    "[PARTIAL_FILL_CHECK] Alpaca broker authentication failed (401). "
                    "Reporting auth_unavailable=True; caller must fail-fast on this in "
                    "live/auto mode rather than treat it as a clean check."
                )
                return {"mismatches": 0, "message": "Broker auth unavailable", "auth_unavailable": True}
            # CRITICAL: Partial fill detection failure - cannot reconcile fill status
            raise RuntimeError(
                f"[PARTIAL_FILL_CHECK FAILED] {type(e).__name__}: {e}. "
                f"Cannot reconcile fill status without valid broker connection."
            ) from e

    def _fetch_account(self) -> Any:
        if not self.broker:
            return {"error": "No broker available (paper trading mode)"}
        try:
            return self.broker.fetch_account()
        except ValueError as e:
            # Handle Alpaca 401/auth errors gracefully in paper mode
            error_str = str(e).lower()
            if "401" in str(e) or "unauthorized" in error_str or "alpaca" in error_str:
                logger.warning(
                    "[RECONCILIATION] Alpaca broker authentication failed (401). "
                    "Gracefully falling back to database portfolio state in paper mode."
                )
                return None  # Return None to trigger DB fallback in run_daily_reconciliation
            # Re-raise other ValueErrors
            raise

    def _fetch_initial_capital(self, cur: PsycopgCursor[Any]) -> float:
        """Get the actual initial capital from broker account history (fail-fast).

        CRITICAL: Does NOT fall back to stale database snapshots. Initial capital is
        required for accurate cumulative return calculation. Stale data (days/months old)
        would severely distort P&L metrics and mask performance issues.

        Raises ValueError if broker history unavailable - reconciliation must fail fast
        rather than use potentially months-old snapshot data.
        """
        try:
            if not self.broker:
                raise ValueError("No broker available in paper trading mode")
            initial_val = self.broker.fetch_initial_capital()
            # Check if dict (error marker) or float (valid data)
            if isinstance(initial_val, dict):
                # CRITICAL: Validate error field exists when dict is returned (fail-fast if missing)
                error_reason = initial_val.get("error")
                if error_reason is None:
                    raise ValueError(
                        f"CRITICAL: Broker returned dict (error marker) but missing required 'error' field. "
                        f"Cannot determine what went wrong. This indicates API contract violation. Response: {initial_val}"
                    )
                raise ValueError(
                    f"CRITICAL: Broker returned empty portfolio history (error: {error_reason}). "
                    "Initial capital cannot be determined from Alpaca. "
                    "Reconciliation requires live broker history for accurate P&L - cannot proceed."
                )
            if initial_val and initial_val > 0:
                logger.info(f"Initial capital from broker history: ${initial_val:,.2f}")
                return initial_val
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(
                f"CRITICAL: Cannot fetch initial capital from Alpaca broker history: {e}. "
                "Initial capital is required for accurate cumulative return calculation. "
                "Check: (1) Is Alpaca API reachable? (2) Does account have portfolio history? "
                "(3) Are credentials valid? Reconciliation halts without live broker data "
                "(stale database snapshots would corrupt P&L metrics)."
            ) from e

        raise ValueError(
            "CRITICAL: Broker returned no portfolio history. "
            "Initial capital cannot be determined from Alpaca. "
            "Reconciliation requires live broker history for accurate P&L - cannot proceed."
        )

    def validate_pnl(self, broker_equity: float, local_equity: float) -> dict[str, Any]:
        """Validate that local P&L matches Alpaca P&L within tolerance.

        Args:
            broker_equity: Equity reported by Alpaca
            local_equity: Equity calculated from local positions and cash

        Returns:
            Dict with validation results: {
                'valid': bool,
                'broker_equity': float,
                'local_equity': float,
                'variance_pct': float,
                'variance_dollars': float,
                'status': 'ok'|'alert'|'critical',
                'message': str
            }
        """
        if broker_equity is None or local_equity is None:
            return {
                "valid": False,
                "broker_equity": broker_equity,
                "local_equity": local_equity,
                "variance_pct": None,
                "variance_dollars": None,
                "status": "error",
                "message": "Cannot validate P&L: missing Alpaca or local equity data",
            }

        if broker_equity <= 0 or local_equity <= 0:
            return {
                "valid": False,
                "broker_equity": broker_equity,
                "local_equity": local_equity,
                "variance_pct": None,
                "variance_dollars": None,
                "status": "error",
                "message": "Cannot validate P&L: equity values must be positive",
            }

        variance_dollars = broker_equity - local_equity
        if broker_equity <= 0:
            raise ValueError("CRITICAL: Broker equity must be positive for variance calculation")
        variance_pct = (variance_dollars / broker_equity) * 100.0

        threshold = 0.1  # 0.1% tolerance

        if abs(variance_pct) <= threshold:
            status = "ok"
            message = f"P&L validated: Alpaca ${broker_equity:,.2f} vs Local ${local_equity:,.2f} (variance {variance_pct:+.3f}%)"
            valid = True
        elif abs(variance_pct) <= 1.0:
            status = "alert"
            message = f"P&L variance ALERT: Alpaca ${broker_equity:,.2f} vs Local ${local_equity:,.2f} (variance {variance_pct:+.3f}%, ${variance_dollars:+,.2f})"
            valid = False
        else:
            status = "critical"
            message = f"P&L MISMATCH CRITICAL: Alpaca ${broker_equity:,.2f} vs Local ${local_equity:,.2f} (variance {variance_pct:+.3f}%, ${variance_dollars:+,.2f}) - verify position prices and trade exit prices"
            valid = False

        return {
            "valid": valid,
            "broker_equity": broker_equity,
            "local_equity": local_equity,
            "variance_pct": variance_pct,
            "variance_dollars": variance_dollars,
            "status": status,
            "message": message,
        }
