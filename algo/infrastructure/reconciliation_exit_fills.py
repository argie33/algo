#!/usr/bin/env python3
"""EXIT-PRICE RECONCILIATION: broker-fill matching, local-mode fallback, staleness audit

Pure extract-method split of the four `DailyReconciliation` methods that reconcile a
trade's `estimated_exit_price` (written by executor_exit_handler.py at close time when the
real fill price isn't known synchronously) against the ACTUAL price the position closed at:

1. `reconcile_exit_fills` - matches Alpaca closed sell orders to trades still awaiting
   reconciliation (via `pending_exit_client_order_id`), folds in any prior partial-exit
   legs' P&L, and writes the real fill price/P&L/R-multiple.
2. `resolve_local_pending_exits` - LOCAL_MODE-only fallback for whatever
   `reconcile_exit_fills` couldn't resolve (no broker, or a live Alpaca call failed): uses
   `price_daily`'s real EOD close for the exit date instead.
3. `audit_stale_estimated_prices` - flags trades that have sat on an estimated exit price
   too long without ever being reconciled by either of the above (live mode only; paper/dry
   modes never get real broker fills, so staleness there is expected).
4. `check_pending_reconciliations` - reports on (and alerts for) trades still pending Phase 7
   price reconciliation.

NO BEHAVIOR CHANGE: every method here is a verbatim relocation of code that used to live
directly on `DailyReconciliation` in reconciliation.py - control flow, thresholds, SQL, and
log messages are unchanged. Comments documenting non-obvious business logic (fix-history
notes, bug-found dates) moved verbatim with the code they describe.

Mixed into DailyReconciliation via multiple inheritance - every `self.` reference here
(self.broker, self.config) resolves normally through the instance regardless of which file
defines the attribute, matching the convention already established by
reconciliation_paper_mode.py / reconciliation_broker_positions.py /
reconciliation_broker_snapshot.py.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date as _date_type
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg2
import requests
from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure.broker_adapter import BrokerAdapter
from algo.reporting import notify

logger = logging.getLogger(__name__)


class ExitFillReconciliationMixin:
    """Mixin providing exit-price reconciliation: broker-fill matching, the LOCAL_MODE
    price_daily fallback, staleness auditing, and the pending-reconciliation report."""

    # Attributes set by DailyReconciliation.__init__ - declared here so mypy resolves them
    # on this mixin (same convention as PaperModeReconciliationMixin's `config` annotation).
    broker: BrokerAdapter | None
    config: dict[str, Any]

    def reconcile_exit_fills(self, cur: PsycopgCursor[Any], reconcile_date: _date_type | None) -> dict[str, Any]:
        """Update DB trade exit prices with actual Alpaca fill prices.

        Phase 4 marks trades 'closed' immediately using the last known market price
        when placing market exit orders before market open. This reconciles those
        estimated prices with actual Alpaca fill prices after market opens.
        """
        try:
            if not self.broker:
                return {"updated": 0, "message": "No broker available (paper trading mode)", "no_broker": True}
            if reconcile_date is None:
                reconcile_date = datetime.now(timezone.utc).date()
            since = datetime.now(timezone.utc) - timedelta(days=2)
            orders = self.broker.fetch_closed_orders(since=since)
            if not orders:
                logger.debug(
                    "No closed orders returned from broker in exit fill reconciliation. "
                    "This is expected if: (1) No orders were placed in the last 2 days, "
                    "(2) All orders were already reconciled. Otherwise, broker API may be unavailable."
                )
                return {"updated": 0, "message": "No closed orders to reconcile", "no_orders_available": True}

            updated = 0

            for order in orders:
                if order.get("status") != "filled" or order.get("side") != "sell":
                    continue
                symbol = order.get("symbol")
                filled_price_str = order.get("filled_avg_price")
                if not symbol or not filled_price_str:
                    raise ValueError(
                        f"[RECONCILIATION CRITICAL] Filled sell order missing symbol or filled_price: {order}"
                    )
                # ORDER-ID CORRELATION FIX (2026-09-05, financial-integrity finding): matching
                # by client_order_id (exact) instead of symbol+date proximity (see module docstring
                # note above reconcile_exit_fills - actually see the fix commit message for the
                # full incident writeup). No match here means this fill isn't one of our trades
                # still awaiting reconciliation (already reconciled, or a foreign/manual order) -
                # skip it rather than guessing which trade it belongs to.
                client_order_id = order.get("client_order_id")
                if not client_order_id:
                    continue
                try:
                    filled_price = float(filled_price_str)
                except (TypeError, ValueError) as e:
                    raise ValueError(
                        f"[RECONCILIATION CRITICAL] Filled price not numeric '{filled_price_str}' for {symbol}"
                    ) from e
                # BUG FOUND 2026-08-10 (NaN-comparison-guard class): float() accepts "nan"/"inf"
                # strings without raising, so a malformed filled_avg_price from the broker JSON
                # would silently pass this `<= 0` check and get written into algo_trades.exit_price.
                if math.isnan(filled_price) or math.isinf(filled_price) or filled_price <= 0:
                    raise ValueError(
                        f"[RECONCILIATION CRITICAL] Filled price invalid {filled_price} for {symbol} - must be > 0"
                    )

                cur.execute("SAVEPOINT reconcile_fill")
                try:
                    cur.execute(
                        """
                        SELECT trade_id, entry_price, stop_loss_price, entry_quantity
                        FROM algo_trades
                        WHERE pending_exit_client_order_id = %s
                          AND symbol = %s
                          AND status = 'closed'
                    """,
                        (client_order_id, symbol),
                    )

                    row = cur.fetchone()
                    if row is None:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        logger.debug(
                            f"[RECONCILIATION] {symbol} fill (client_order_id={client_order_id}) does not match any trade still awaiting reconciliation - skipping."
                        )
                        continue

                    trade_id, entry_price, stop_loss_price, entry_qty = row
                    if entry_price is None or stop_loss_price is None or entry_qty is None:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) missing entry_price, stop_loss_price, or entry_qty - cannot reconcile"
                        )

                    try:
                        entry_price = float(entry_price)
                        stop_loss_price = float(stop_loss_price)
                        # float (not int): algo_trades.entry_quantity is NUMERIC(18,4) - real
                        # fractional-share entries exist in this DB. int() truncation here fed
                        # a too-small cost basis/risk denominator into original_cost_basis/
                        # original_risk_dollars below for multi-leg fills - same bug class
                        # already fixed in executor_exit_handler.py's _compute_cumulative_pnl
                        # (the synchronous exit path this function mirrors for async fills).
                        entry_qty = float(entry_qty)
                    except (ValueError, TypeError) as e:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has non-numeric price/qty - cannot reconcile"
                        ) from e

                    if (
                        math.isnan(entry_price)
                        or math.isinf(entry_price)
                        or math.isnan(stop_loss_price)
                        or math.isinf(stop_loss_price)
                        or math.isnan(entry_qty)
                        or math.isinf(entry_qty)
                        or entry_price <= 0
                        or stop_loss_price <= 0
                        or entry_qty <= 0
                    ):
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has invalid prices/qty (entry={entry_price}, stop={stop_loss_price}, qty={entry_qty}) - must be > 0"
                        )

                    # CRITICAL: use THIS order's actual filled quantity, not entry_qty (the
                    # original full position size). For a trade closed via multiple partial
                    # exits (T1/T2 profit-taking before a final stop/target exit), this order
                    # only sold the shares remaining at final-exit time - using entry_qty here
                    # would attribute the entire original position's P&L to just this leg's
                    # price, silently discarding what the earlier legs actually realized. This
                    # is the same financial-integrity bug class already found and fixed for the
                    # synchronous exit path (see executor_exit_handler.py's
                    # _compute_cumulative_pnl docstring, "2026-07-21 financial-integrity audit")
                    # - this reconciliation fallback path (for fills whose price wasn't known
                    # synchronously) never got the same fix.
                    filled_qty_str = order.get("filled_qty")
                    if not filled_qty_str:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Filled sell order missing filled_qty for {symbol}: {order}"
                        )
                    try:
                        filled_qty = float(filled_qty_str)
                    except (TypeError, ValueError) as e:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] filled_qty not numeric '{filled_qty_str}' for {symbol}"
                        ) from e
                    if math.isnan(filled_qty) or math.isinf(filled_qty) or filled_qty <= 0:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] filled_qty invalid {filled_qty} for {symbol} - must be > 0"
                        )

                    filled_dec = Decimal(str(filled_price))
                    entry_dec = Decimal(str(entry_price))
                    entry_qty_dec = Decimal(str(entry_qty))
                    leg_pnl_dollars_dec = ((filled_dec - entry_dec) * Decimal(str(filled_qty))).quantize(
                        Decimal("0.01"), ROUND_HALF_UP
                    )
                    risk = entry_price - stop_loss_price
                    if risk <= 0:
                        cur.execute("RELEASE SAVEPOINT reconcile_fill")
                        raise ValueError(
                            f"[RECONCILIATION CRITICAL] Trade {trade_id} ({symbol}) has invalid risk={risk}: "
                            f"stop_loss_price ({stop_loss_price}) >= entry_price ({entry_price}). "
                            f"Cannot compute R-multiple with invalid stop price."
                        )

                    # Fold in any earlier partial-exit legs' realized P&L (mirrors
                    # executor_exit_handler.py's _compute_cumulative_pnl exactly).
                    cur.execute(
                        """
                        SELECT COALESCE(SUM((details->>'pnl_dollars')::numeric), 0)
                        FROM algo_audit_log
                        WHERE action_type LIKE 'exit_%%'
                          AND (details->>'trade_id') = %s
                          AND (details->>'full_exit')::boolean = false
                        """,
                        (trade_id,),
                    )
                    prior_partial_pnl_row = cur.fetchone()
                    prior_partial_pnl_dec = (
                        Decimal(str(prior_partial_pnl_row[0])) if prior_partial_pnl_row else Decimal(0)
                    )

                    if prior_partial_pnl_dec == 0:
                        # No prior partial legs - simple single-leg case, same formula as before.
                        pnl_dollars = float(leg_pnl_dollars_dec)
                        pnl_pct = float(
                            ((filled_dec - entry_dec) / entry_dec * Decimal(100)).quantize(
                                Decimal("0.01"), ROUND_HALF_UP
                            )
                        )
                        exit_r_multiple = float(
                            ((filled_dec - entry_dec) / Decimal(str(risk))).quantize(Decimal("0.01"), ROUND_HALF_UP)
                        )
                    else:
                        cumulative_pnl_dec = (prior_partial_pnl_dec + leg_pnl_dollars_dec).quantize(
                            Decimal("0.01"), ROUND_HALF_UP
                        )
                        original_cost_basis = entry_dec * entry_qty_dec
                        original_risk_dollars = Decimal(str(risk)) * entry_qty_dec
                        pnl_dollars = float(cumulative_pnl_dec)
                        pnl_pct = float(
                            (cumulative_pnl_dec / original_cost_basis * Decimal(100)).quantize(
                                Decimal("0.01"), ROUND_HALF_UP
                            )
                        )
                        exit_r_multiple = float(
                            (cumulative_pnl_dec / original_risk_dollars).quantize(Decimal("0.01"), ROUND_HALF_UP)
                        )
                        logger.info(
                            f"[RECONCILIATION MULTI_LEG] {symbol} trade {trade_id}: cumulative P&L across all "
                            f"legs ${pnl_dollars:.2f} (prior partial legs: ${float(prior_partial_pnl_dec):.2f}, "
                            f"final leg: ${float(leg_pnl_dollars_dec):.2f})"
                        )

                    # Check if this trade had an estimated exit price (Phase 4 pre-market exit)
                    cur.execute(
                        "SELECT estimated_exit_price FROM algo_trades WHERE trade_id = %s",
                        (trade_id,),
                    )
                    est_row = cur.fetchone()
                    estimated_price = float(est_row[0]) if est_row is not None and est_row[0] is not None else None

                    # Calculate reconciliation note with variance if estimated price exists
                    reconciliation_note = None
                    if estimated_price and estimated_price > 0:
                        if filled_price is None or filled_price <= 0:
                            logger.warning(
                                f"[RECONCILIATION] Cannot calculate variance for {trade_id}: "
                                f"filled_price={filled_price} is not positive. Skipping variance calculation."
                            )
                        else:
                            variance_pct = (filled_price - estimated_price) / estimated_price * 100.0
                            reconciliation_note = f"Actual: ${filled_price:.2f} vs Estimated: ${estimated_price:.2f} ({variance_pct:+.2f}%)"

                    cur.execute(
                        """
                        UPDATE algo_trades
                        SET exit_price = %s, profit_loss_pct = %s,
                            profit_loss_dollars = %s, exit_r_multiple = %s,
                            exit_price_reconciled_at = CURRENT_TIMESTAMP,
                            reconciliation_note = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE trade_id = %s
                    """,
                        (
                            filled_price,
                            pnl_pct,
                            pnl_dollars,
                            exit_r_multiple,
                            reconciliation_note,
                            trade_id,
                        ),
                    )

                    cur.execute("RELEASE SAVEPOINT reconcile_fill")
                    updated += 1
                    logger.info(f"   Exit fill reconciled: {symbol} {trade_id} @ ${filled_price:.2f} ({pnl_pct:.1f}%)")
                except (psycopg2.DatabaseError, ValueError, TypeError) as e:
                    try:
                        cur.execute("ROLLBACK TO SAVEPOINT reconcile_fill")
                    except psycopg2.DatabaseError as rollback_err:
                        if "does not exist" not in str(rollback_err):
                            raise
                        logger.warning(
                            f"[RECONCILIATION] Savepoint missing (transaction may be aborted), skipping rollback for {symbol}"
                        )
                    logger.error(
                        f"[RECONCILIATION] Exit fill reconciliation failed for {symbol}: {e}. "
                        f"Trade exit price could not be reconciled with Alpaca fill price. "
                        f"Skipping this trade but continuing reconciliation (partial reconciliation detected)."
                    )

            return {
                "updated": updated,
                "message": f"Reconciled {updated} exit fills with actual Alpaca prices",
            }
        except (
            ValueError,
            requests.RequestException,
            json.JSONDecodeError,
            psycopg2.DatabaseError,
        ) as e:
            logger.error(
                f"[RECONCILIATION CRITICAL] Exit fill reconciliation failed: {e}. "
                "Cannot reconcile trade exit prices with actual Alpaca fill prices. "
                "This prevents accurate P&L calculation and risk reporting. "
                "Reconciliation must fail explicitly rather than silently skip exit price validation."
            )
            raise ValueError(
                f"CRITICAL: Exit fill reconciliation failed: {e}. "
                "Cannot reconcile exit prices with broker fills. "
                "Reconciliation requires accurate exit prices for P&L validation."
            ) from e

    def resolve_local_pending_exits(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """LOCAL_MODE-only: resolve trades stuck with NULL P&L pending broker fill reconciliation.

        reconcile_exit_fills() (above) is the only code path that ever resolves an
        estimated_exit_price into a real fill price, and it requires self.broker to be set AND a
        successful live Alpaca call - both unavailable in local dev (no broker, or placeholder
        credentials that can never authenticate). Without this, any trade closed by
        phase9_reconciliation.py's _record_closed_positions_exits() stays profit_loss_dollars=NULL
        forever, permanently invisible to win_rate/consecutive_losses/realized P&L in local dev.

        Uses price_daily's real EOD close for the exit symbol/date as the fill price - this is
        genuine market data (not fabricated), consistent with governance's real-data-only rule,
        unlike the fixed bug where a stale current_price silently produced a fake $0.00 P&L.

        Resolves trades whose exit_date has an actual close on file (today or earlier). If price_daily
        close is available for exit_date, uses it to calculate P&L. For same-day trades where
        entry_price = estimated_exit_price (no price movement), can use the estimate if price_daily
        data hasn't loaded yet. Otherwise leaves trade pending for next run.
        """
        cur.execute("""
            SELECT trade_id, symbol, entry_price, stop_loss_price, entry_quantity, exit_date,
                   estimated_exit_price
            FROM algo_trades
            WHERE status = 'closed'
              AND profit_loss_dollars IS NULL
              AND estimated_exit_price IS NOT NULL
              AND exit_date <= CURRENT_DATE
            """)
        pending = cur.fetchall()
        if not pending:
            return {"resolved": 0, "message": "No local-mode pending exits to resolve"}

        resolved = 0
        for trade_id, symbol, entry_price, stop_loss_price, entry_qty, exit_date, estimated_exit_price in pending:
            if entry_price is None or stop_loss_price is None or entry_qty is None:
                logger.warning(
                    f"[LOCAL EXIT RESOLUTION] {trade_id} ({symbol}) missing entry_price/stop_loss_price/"
                    "entry_quantity - cannot resolve, leaving pending"
                )
                continue

            # Always prefer price_daily's real close for exit_date over estimated_exit_price -
            # the estimate was itself derived from algo_positions.current_price at close time,
            # which is only as fresh as the last price sync before the position closed (see
            # _record_closed_positions_exits's comment above). For same-day trades in particular,
            # that sync often ran before the morning loader landed today's close, so blindly
            # trusting the estimate reproduces the exact "stale current_price -> fake $0.00 P&L"
            # bug this function exists to fix. Only fall back to the estimate when price_daily
            # genuinely has no close yet for exit_date (e.g. resolving before today's data loads).
            cur.execute(
                """
                SELECT close FROM price_daily
                WHERE symbol = %s AND date = %s AND (data_unavailable IS NOT TRUE)
                """,
                (symbol, exit_date),
            )
            price_row = cur.fetchone()
            if price_row is not None and price_row[0] is not None:
                fill_price = Decimal(str(price_row[0]))
                price_source = f"price_daily EOD close for {exit_date}"
            elif exit_date == datetime.now(timezone.utc).date() and entry_price == estimated_exit_price:
                fill_price = Decimal(str(estimated_exit_price))
                price_source = "estimated_exit_price (no price_daily close for today yet)"
                logger.debug(
                    f"[LOCAL EXIT RESOLUTION] Same-day close for {trade_id} ({symbol}): "
                    f"using estimated_exit_price ${float(fill_price):.2f}"
                )
            else:
                logger.debug(
                    f"[LOCAL EXIT RESOLUTION] No price_daily close yet for {symbol} on {exit_date} "
                    f"- leaving {trade_id} pending"
                )
                continue

            # CRITICAL FIX: For multi-leg exits, sum prior partial exit P&L with this final leg's P&L.
            # When a position closes via multiple partial exits (T1/T2 profit-taking before final
            # stop/target), each exit fills at a different price. This function receives fill_price
            # for the FINAL leg only, but must report total realized P&L across ALL legs.
            # Without this, multi-leg exits would report only the final leg's P&L (or loss),
            # discarding every dollar from earlier legs - exact same bug that was already fixed
            # in reconcile_exit_fills() and executor_exit_handler.py's _compute_cumulative_pnl.
            #
            # Prior partial leg data comes from algo_audit_log's JSONB 'details' column (this
            # table has no top-level trade_id/event_type/amount/quantity columns - see migration
            # 094a_create_algo_audit_log_table.py - only action_type and details JSONB). Exit
            # legs are logged by executor_exit_handler.py as action_type='exit_{stage}' with
            # details containing trade_id/pnl_dollars/shares_exited/full_exit (see its
            # _compute_cumulative_pnl and reconcile_exit_fills() above for the identical query).
            prior_pnl_dollars = Decimal("0")
            prior_exit_qty = Decimal("0")
            cur.execute(
                """
                SELECT COALESCE(SUM((details->>'pnl_dollars')::numeric), 0),
                       COALESCE(SUM((details->>'shares_exited')::numeric), 0)
                FROM algo_audit_log
                WHERE action_type LIKE 'exit_%%'
                  AND (details->>'trade_id') = %s
                  AND (details->>'full_exit')::boolean = false
                """,
                (trade_id,),
            )
            audit_row = cur.fetchone()
            if audit_row:
                prior_pnl_dollars = Decimal(str(audit_row[0])) if audit_row[0] is not None else Decimal("0")
                prior_exit_qty = Decimal(str(audit_row[1])) if audit_row[1] is not None else Decimal("0")

            # Calculate P&L for THIS leg only (not cumulative yet)
            entry_dec = Decimal(str(entry_price))
            qty_dec = Decimal(str(entry_qty))
            # This leg's P&L: (fill_price - entry_price) * remaining_qty
            # remaining_qty = entry_qty - prior_exit_qty (amount of position resolved by this exit)
            this_leg_qty = qty_dec - prior_exit_qty
            this_leg_pnl = (fill_price - entry_dec) * this_leg_qty if this_leg_qty > 0 else Decimal("0")
            # Cumulative P&L: prior legs + this leg
            cumulative_pnl = prior_pnl_dollars + this_leg_pnl

            # Risk/reward based on TOTAL realized P&L, not just this leg
            # R multiple = total_pnl / (risk_per_share * total_entry_qty)
            risk_per_share = float(entry_price) - float(stop_loss_price)
            if risk_per_share > 0:
                total_risk = Decimal(str(risk_per_share)) * qty_dec
                exit_r_multiple = float((cumulative_pnl / total_risk).quantize(Decimal("0.01"), ROUND_HALF_UP))
            else:
                exit_r_multiple = None

            # P&L % based on total realized P&L relative to total position cost
            pnl_pct = float(
                (cumulative_pnl / (entry_dec * qty_dec) * Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
            )
            pnl_dollars = float(cumulative_pnl.quantize(Decimal("0.01"), ROUND_HALF_UP))

            cur.execute(
                """
                UPDATE algo_trades
                SET exit_price = %s, profit_loss_dollars = %s, profit_loss_pct = %s,
                    exit_r_multiple = %s, exit_price_reconciled_at = CURRENT_TIMESTAMP,
                    reconciliation_note = %s, updated_at = CURRENT_TIMESTAMP
                WHERE trade_id = %s
                """,
                (
                    float(fill_price),
                    pnl_dollars,
                    pnl_pct,
                    exit_r_multiple,
                    f"[LOCAL_MODE] Resolved via {price_source} (no live broker available to confirm actual fill)",
                    trade_id,
                ),
            )
            resolved += 1
            logger.info(
                f"[LOCAL EXIT RESOLUTION] {trade_id} ({symbol}): resolved P&L ${pnl_dollars:+.2f} "
                f"({pnl_pct:+.2f}%) using {exit_date} close ${float(fill_price):.2f}"
            )

        return {"resolved": resolved, "message": f"Resolved {resolved} local-mode pending exit(s)"}

    def audit_stale_estimated_prices(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Audit for trades with estimated exit prices that haven't been reconciled to the
        broker's actual fill price yet.

        executor_exit_handler.py writes estimated_exit_price + status='closed' immediately on
        exit (PENDING_FILL_RECONCILIATION) when the real fill price isn't known synchronously;
        exit_price_reconciled_at is set once a later reconciliation pass confirms the real fill.
        A row that stays unreconciled too long means P&L/exit_r_multiple are still computed from
        a guess, not the broker's actual fill - this audit surfaces that before it goes unnoticed.

        In paper trading mode, reconciliation never happens (no real broker fills), so estimated
        prices are expected to remain unreconciled indefinitely. Skip audit in paper mode.

        BUG FOUND 2026-08-11: "dry" mode is equally a no-real-broker-fills local mode (same
        allowlist distinction already fixed elsewhere tonight, e.g. executor.py's
        credential-fetch handling) - a bare `== "paper"` here missed it, so dry mode ran this
        audit and could raise false ALERT/CRITICAL status for exit prices that will never
        reconcile in dry mode either.

        Returns dict: {'status': 'OK'|'ALERT'|'CRITICAL', 'message': str, 'stale_trade_count': int,
        'stale_trades': list[dict]}.
        """
        # Skip audit in paper/dry trading mode - broker reconciliation never happens, so
        # unreconciled estimated prices are expected and harmless. Only audit in live mode
        # where real fills matter.
        is_paper_mode = self.config.get("execution_mode") in ("paper", "dry")
        if is_paper_mode:
            return {
                "status": "OK",
                "message": "Paper trading mode: exit price reconciliation skipped (no real broker fills)",
                "stale_trade_count": 0,
                "stale_trades": [],
            }

        stale_threshold = timedelta(hours=2)
        critical_threshold = timedelta(hours=24)

        cur.execute("""SELECT trade_id, symbol, estimated_exit_price, exit_time
               FROM algo_trades
               WHERE estimated_exit_price IS NOT NULL
                 AND exit_price_reconciled_at IS NULL
               ORDER BY exit_time ASC""")
        rows = cur.fetchall()

        if not rows:
            return {
                "status": "OK",
                "message": "No unreconciled estimated exit prices.",
                "stale_trade_count": 0,
                "stale_trades": [],
            }

        now = datetime.now(timezone.utc)
        stale_trades: list[dict[str, Any]] = []
        max_age = timedelta(0)
        for trade_id, symbol, estimated_exit_price, exit_time in rows:
            if exit_time is None:
                # No exit_time recorded - can't compute age, but flag it as data quality issue
                age = critical_threshold + timedelta(seconds=1)
            else:
                # algo_trades.exit_time is a `timestamp without time zone` column written via
                # SQL CURRENT_TIMESTAMP, so a naive value here is in the DB session's local
                # wall-clock timezone (utils/bulk_insert_manager.py's documented convention),
                # not UTC - confirmed live this session's actual `SHOW timezone` is
                # America/Chicago, 5+ hours off UTC. Mislabeling it as UTC via
                # .replace(tzinfo=timezone.utc) silently inflated age by that offset, which
                # exceeds the 2h stale_threshold below on its own - every unreconciled exit
                # price would falsely alert as stale regardless of true age. Same bug class
                # already fixed in algo/risk/market_exposure.py's cache-age check,
                # algo/trading/pretrade_checks.py's re-entry cooldown, and
                # algo/monitoring/position_monitor.py's stale-order check.
                if exit_time.tzinfo:
                    exit_time_utc = exit_time
                else:
                    from utils.db.timezone_utils import get_db_timezone

                    naive_tz = get_db_timezone()
                    exit_time_utc = exit_time.replace(tzinfo=naive_tz)
                age = now - exit_time_utc
            if age >= stale_threshold:
                stale_trades.append(
                    {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "estimated_exit_price": float(estimated_exit_price),
                        "exit_time": exit_time.isoformat() if exit_time else None,
                        "age_hours": round(age.total_seconds() / 3600, 1),
                    }
                )
                max_age = max(max_age, age)

        if not stale_trades:
            return {
                "status": "OK",
                "message": f"{len(rows)} unreconciled estimated exit price(s), all under {stale_threshold}.",
                "stale_trade_count": 0,
                "stale_trades": [],
            }

        status = "CRITICAL" if max_age >= critical_threshold else "ALERT"
        symbols = ", ".join(f"{t['symbol']}({t['age_hours']}h)" for t in stale_trades[:10])
        message = (
            f"[STALE_PRICE_AUDIT] {len(stale_trades)} trade(s) still on estimated exit price "
            f"past the {stale_threshold} threshold: {symbols}" + ("..." if len(stale_trades) > 10 else "")
        )
        return {
            "status": status,
            "message": message,
            "stale_trade_count": len(stale_trades),
            "stale_trades": stale_trades,
        }

    def check_pending_reconciliations(self, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Identify and report on trades pending Phase 7 price reconciliation.

        Trades with estimated exit prices (Phase 4 pre-market exits) that haven't
        been reconciled with actual Alpaca fill prices. Helps diagnose Phase 7
        failures or delays that leave estimated prices permanent.
        """
        try:
            cur.execute("""
                SELECT trade_id, symbol, exit_date, exit_price, estimated_exit_price,
                       exit_price_reconciled_at, reconciliation_note
                FROM algo_trades
                WHERE estimated_exit_price IS NOT NULL
                  AND exit_price_reconciled_at IS NULL
                ORDER BY exit_date DESC
            """)
            pending = cur.fetchall()

            if not pending:
                return {"pending_count": 0, "message": "No pending reconciliations"}

            pending_list = []
            for (
                trade_id,
                symbol,
                exit_date,
                exit_price,
                est_price,
                _recon_at,
                note,
            ) in pending:
                variance_pct = None
                if exit_price is not None and est_price is not None:
                    try:
                        exit_price_f = float(exit_price)
                        est_price_f = float(est_price)
                        if est_price_f > 0:
                            variance_pct = (exit_price_f - est_price_f) / est_price_f * 100
                    except (ValueError, TypeError):
                        variance_pct = None
                pending_list.append(
                    {
                        "trade_id": trade_id,
                        "symbol": symbol,
                        "exit_date": exit_date,
                        "estimated_price": float(est_price) if est_price is not None else None,
                        "current_exit_price": float(exit_price) if exit_price is not None else None,
                        "variance_pct": variance_pct,
                        "note": note,
                        "days_pending": ((datetime.now(timezone.utc).date() - exit_date).days if exit_date else None),
                    }
                )

            # Log critical alert if any reconciliations are stuck (> 1 day old)
            stuck = [p for p in pending_list if p["days_pending"] and p["days_pending"] > 1]
            if stuck:
                stuck_examples = ", ".join(["{} {}".format(p["symbol"], p["trade_id"]) for p in stuck[:3]])
                stuck_message = (
                    f"RECONCILIATION STUCK: {len(stuck)} trades with estimated exit prices "
                    "stuck > 1 day without Alpaca price reconciliation. "
                    f"Examples: {stuck_examples}"
                )
                logger.critical(stuck_message)
                # BUG FOUND 2026-09-01 (real-money-readiness pass): this only ever reached
                # logger.critical() - unlike every other CRITICAL condition in this same
                # file (broker cash missing/negative, account fetch failure, portfolio_value
                # missing, all of which call notify() a few hundred lines above/below this
                # one), a stuck reconciliation never reached a real alert channel. Effect:
                # profit_loss_dollars/portfolio_value/drawdown get silently computed off a
                # stale ESTIMATED exit price indefinitely, with no operator ever notified -
                # same "computed but never delivered" bug class already found and fixed for
                # Phase 9's VaR/concentration/beta alerts (commit 5ac092eea).
                try:
                    notify(
                        "critical",
                        title="Trade Reconciliation Stuck",
                        message=stuck_message,
                    )
                except Exception as e:
                    logger.error(f"Failed to send stuck-reconciliation notification (non-blocking): {e}", exc_info=True)

            return {
                "pending_count": len(pending_list),
                "stuck_count": len(stuck),
                "pending": pending_list,
                "message": f"{len(pending_list)} trades pending reconciliation ({len(stuck)} stuck > 1d)",
            }
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to check pending reconciliations: {e}", exc_info=True)
            raise RuntimeError(
                f"[RECONCILIATION] Cannot check pending reconciliations due to data error: {e}. "
                f"Position reconciliation is critical for accurate portfolio reporting. "
                f"Reconciliation check must fail explicitly rather than return incomplete data."
            ) from e
        except ZeroDivisionError as e:
            logger.error(f"[RECONCILIATION] Division by zero in pending reconciliation check: {e}", exc_info=True)
            raise RuntimeError(
                "[RECONCILIATION] Variance calculation failed with division by zero. "
                "This indicates missing or invalid price data in pending trade reconciliations. "
                "Check database consistency and retry."
            ) from e
