#!/usr/bin/env python3

import logging
import math
import os
import traceback
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import psycopg2

from algo.orchestrator.config_validator import validate_phase_config
from algo.orchestrator.phase9_reporting import (
    _compute_performance_metrics,
    _compute_risk_metrics,
    _generate_daily_report,
    _populate_signal_trade_performance,
    _update_daily_metrics,
)
from algo.orchestrator.phase_result import PhaseResult
from utils.db.advisory_locks import (
    ALGO_POSITIONS_LOCK_ID,
    ALGO_TRADES_LOCK_ID,
    acquire_advisory_lock,
    release_advisory_lock,
)
from utils.db.context import DatabaseContext
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)


def _run_reconciliation_step(
    config: Any,
    run_date: _date,
    log_phase_result_fn: Callable[..., Any],
    dry_run: bool,
) -> tuple[bool, dict[str, Any]]:
    """Run initial reconciliation step and validate results."""
    from algo.infrastructure.reconciliation import DailyReconciliation

    recon = DailyReconciliation(config)

    try:
        result = recon.run_daily_reconciliation(run_date, dry_run=dry_run)
    except Exception as e:
        error_str = str(e).lower()
        is_alpaca_auth_error = "401" in str(e) or "403" in str(e) or "unauthorized" in error_str
        # "auto" is this system's real live-trading mode (see this session's other
        # execution_mode fixes) - both branches below ultimately raise regardless, so this
        # doesn't change control flow, only which error message an "auto" mode auth failure
        # gets logged/raised under (previously always the misleading "[PHASE 9 PAPER MODE]"
        # one, obscuring that a live deployment's Alpaca credentials are the real problem).
        is_paper_mode = config.get("execution_mode") == "paper"

        if is_alpaca_auth_error and is_paper_mode:
            logger.error(
                f"[PHASE 9 PAPER MODE] Alpaca API error ({type(e).__name__}): {e}. "
                f"Paper mode reconciliation requires either: "
                f"(1) Alpaca credentials in AWS Secrets Manager (algo/alpaca secret), or "
                f"(2) database state that's in sync. Cannot proceed with hardcoded defaults ($100k) as that masks data issues."
            )
            raise RuntimeError(
                f"[PHASE 9] Paper mode reconciliation failed: {type(e).__name__}: {str(e)[:200]}. "
                f"Check Alpaca credentials in AWS Secrets Manager or database sync state."
            ) from e
        else:
            # CRITICAL FIX: this branch covers every non-paper-mode failure, including a real
            # Alpaca auth error during live ("auto") trading - the highest-stakes case, since
            # Phase 9 reconciliation failure can gate a governance halt (see phase_executor.py
            # / the run() halt-wiring below). It still raised the literal string "Paper mode
            # reconciliation failed" regardless of actual execution_mode - a live-mode incident
            # reads to on-call as an expected, non-critical local-dev condition. Only the
            # logger.error() branch above was actually fixed by the comment at the top of this
            # try/except; the raised message itself was never updated to match.
            execution_mode = config.get("execution_mode", "unknown")
            raise RuntimeError(
                f"[PHASE 9] Reconciliation failed (execution_mode={execution_mode}): {type(e).__name__}: {str(e)[:200]}"
            ) from e

    if "success" not in result:
        raise ValueError(
            "Reconciliation result missing 'success' field. "
            f"Available keys: {list(result.keys())}. "
            "Check DailyReconciliation.run_daily_reconciliation() implementation."
        )

    reconciliation_succeeded = result["success"]
    status = "success" if reconciliation_succeeded else "error"

    if reconciliation_succeeded:
        required_keys = ["portfolio_value", "positions", "unrealized_pnl"]
        missing_keys = [k for k in required_keys if k not in result or result[k] is None]
        if missing_keys:
            logger.error(
                f"[PHASE 9 CRITICAL] Reconciliation reported success but missing critical data: {missing_keys}. "
                f"Result keys available: {list(result.keys())}. "
                f"Cannot proceed with hardcoded defaults as that masks data sync issues. "
                f"Check: (1) DailyReconciliation implementation, (2) Alpaca API connectivity, "
                f"(3) algo_portfolio_snapshots table state"
            )
            raise ValueError(f"Reconciliation succeeded but missing critical data: {missing_keys}")

        # Defensive formatting for reconciliation summary - handle None values gracefully
        try:
            pf_val = result["portfolio_value"]
            pos_count = result["positions"]
            pnl = result["unrealized_pnl"]

            pf_str = f"{float(pf_val):,.2f}" if pf_val is not None else "N/A"
            pos_str = f"{int(pos_count)}" if pos_count is not None else "N/A"
            pnl_str = f"{float(pnl):+,.2f}" if pnl is not None else "N/A"

            summary = f"Portfolio ${pf_str}, {pos_str} positions, unrealized P&L ${pnl_str}"
        except (ValueError, TypeError) as fmt_err:
            logger.error(f"[PHASE 9] Failed to format reconciliation summary: {fmt_err}")
            summary = "Portfolio: data formatting error"
    else:
        error_msg = result.get("error")
        if not error_msg:
            raise ValueError(
                f"CRITICAL: Reconciliation failed but error message missing. "
                f"Result keys: {list(result.keys())}. "
                f"Cannot proceed without understanding why reconciliation failed."
            )
        summary = error_msg
    log_phase_result_fn(9, "reconciliation", status, summary)
    return reconciliation_succeeded, result


def _validate_pnl_step(
    recon: Any,
    result: dict[str, Any],
    log_phase_result_fn: Callable[..., Any],
) -> tuple[str, str]:
    pnl_validation_status = "warn"
    pnl_validation_summary = "N/A"
    try:
        if recon.broker is None:
            logger.warning("[PHASE 9 P&L] Paper mode: broker unavailable, skipping P&L validation")
            pnl_validation_status = "warn"
            pnl_validation_summary = "Paper mode - no broker account"
            return pnl_validation_status, pnl_validation_summary
        account_data = recon.broker.fetch_account()
        if account_data and result.get("success"):
            # CRITICAL FIX: No fallback sequence - require explicit 'equity' field from broker
            # Finance app requirement: must use primary broker-of-record field, not alternates
            # Fallback patterns hide which field is actually in use and can mask broker API changes
            broker_equity = account_data.get("equity")
            if broker_equity is None:
                available_keys = list(account_data.keys())
                logger.error(
                    "[PHASE 9 P&L VALIDATION FAIL-FAST] Broker account data missing required 'equity' field. "
                    f"Cannot validate P&L reconciliation without Alpaca's primary account equity value. "
                    f"Available keys: {available_keys}. "
                    f"Check: (1) Alpaca API schema (broker adapter may be outdated), "
                    f"(2) Broker connector implementation returns correct field name."
                )
                raise ValueError(
                    "Broker 'equity' field required for P&L validation. "
                    "Cannot proceed with fallback fields - must use primary broker source of truth."
                )

            if "portfolio_value" not in result:
                raise ValueError(
                    "Reconciliation succeeded but missing portfolio_value (required for P&L validation). "
                    f"Available keys: {list(result.keys())}"
                )
            local_equity = result["portfolio_value"]

            pnl_check = recon.validate_pnl(broker_equity, local_equity)
            pnl_validation_status = pnl_check["status"]
            pnl_validation_summary = pnl_check["message"]

            if pnl_check["status"] == "ok":
                logger.info(f"[PHASE 9 P&L VALIDATION] {pnl_check['message']}")
            elif pnl_check["status"] == "alert":
                logger.warning(f"[PHASE 9 P&L VALIDATION] {pnl_check['message']}")
            else:  # critical
                logger.critical(f"[PHASE 9 P&L VALIDATION] {pnl_check['message']}")
                # GOVERNANCE: a critical P&L divergence is, per validate_pnl()'s own
                # docstring, real data corruption between broker and local state. Every
                # other critical branch in this file surfaces via notify(); this one only
                # logged, so a >1% divergence could go unnoticed unless someone was
                # watching logs at the moment it happened.
                try:
                    from algo.reporting import notify

                    notify(
                        severity="critical",
                        title="Phase 9 P&L Divergence",
                        message=pnl_check["message"],
                        details={"broker_equity": broker_equity, "local_equity": local_equity},
                    )
                except (ValueError, TypeError, RuntimeError) as notify_err:
                    logger.error(f"Failed to send P&L divergence notification: {notify_err}")
        else:
            pnl_validation_summary = "Skipped (reconciliation failed or no Broker data)"
    except (ValueError, RuntimeError, KeyError) as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] P&L validation failed: {e}. "
            f"Cannot proceed with reconciliation when P&L validation unavailable. "
            f"Check broker connectivity, account sync, and local portfolio state."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e
    finally:
        log_phase_result_fn(9, "pnl_validation", pnl_validation_status, pnl_validation_summary)
    return pnl_validation_status, pnl_validation_summary


def _audit_exit_prices_step(
    recon: Any,
    log_phase_result_fn: Callable[..., Any],
) -> None:
    """Audit stale estimated exit prices."""
    try:
        with DatabaseContext("read") as audit_cur:
            stale_audit = recon.audit_stale_estimated_prices(audit_cur)
            status = stale_audit.get("status")
            if status is None:
                raise ValueError(f"Exit price audit result missing 'status' field. Keys: {list(stale_audit.keys())}")

            if status != "OK":
                msg = stale_audit.get("message")
                if msg is None:
                    raise ValueError(
                        f"Exit price audit status '{status}' but message missing. Keys: {list(stale_audit.keys())}"
                    )
                if status == "CRITICAL":
                    logger.critical(f"[PHASE 9 AUDIT] Stale estimated prices detected: {msg}")
                else:
                    logger.warning(f"[PHASE 9 AUDIT] Stale estimated prices detected: {msg}")
                log_phase_result_fn(9, "exit_reconciliation_audit", "warn", msg)
            else:
                logger.info("[PHASE 9 AUDIT] All exit prices reconciled properly")
    except (psycopg2.DatabaseError, psycopg2.OperationalError, KeyError, ValueError) as e:
        error_msg = (
            f"[PHASE 9 CRITICAL] Exit price audit failed: {e}. "
            f"Cannot proceed when exit prices cannot be verified. "
            f"Check database connectivity and reconciliation state."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e


def _populate_missing_trade_ids_arr(log_phase_result_fn: Callable[..., Any]) -> None:
    """Populate trade_ids_arr for positions that have no trade_ids set.

    CRITICAL FIX (Session 19): Architecture issue - position_sync runs in Phase 1 before
    Phase 8 creates entry trades. Positions created by Phase 8 never get their trade_ids_arr
    populated, causing circuit breaker to fail with "orphaned trade_ids_arr" errors.

    This function runs in Phase 9 (after Phase 8 has created trades) to populate missing
    trade_ids_arr by joining positions to their corresponding trades.
    """
    try:
        with DatabaseContext("write") as cur:
            # Find positions with missing/NULL trade_ids_arr
            cur.execute("""
                SELECT COUNT(*) FROM algo_positions
                WHERE status = 'open'
                AND (trade_ids_arr IS NULL OR array_length(trade_ids_arr, 1) IS NULL)
            """)
            missing_count = cur.fetchone()[0]

            if missing_count > 0:
                logger.info(f"[PHASE 9] Found {missing_count} positions with missing trade_ids_arr - populating...")

                # Update positions with their trade_ids from corresponding trades.
                # Session 81: status filter broadened from ('open', 'filled') to
                # TradeStatus.all_open() - a trade sitting in 'partially_filled'/
                # 'paper_pending'/'pending'/'active' at repair time previously fell out of
                # the ARRAY_AGG, so this repair silently failed to fix exactly the
                # positions it exists to fix. Matches position_sync.py's LINKED_TRADE_STATUSES fix.
                linked_statuses = TradeStatus.all_open()
                status_placeholders = ",".join(["%s"] * len(linked_statuses))
                cur.execute(
                    f"""
                    UPDATE algo_positions ap SET
                        trade_ids_arr = t_agg.trade_ids,
                        updated_at = NOW()
                    FROM (
                        SELECT position_id, ARRAY_AGG(DISTINCT trade_id::text) as trade_ids
                        FROM algo_trades
                        WHERE status IN ({status_placeholders})
                        GROUP BY position_id
                    ) t_agg
                    WHERE ap.position_id = t_agg.position_id
                    AND (ap.trade_ids_arr IS NULL OR array_length(ap.trade_ids_arr, 1) IS NULL)
                    """,
                    linked_statuses,
                )

                updated_count = cur.rowcount
                logger.info(f"[PHASE 9] Populated trade_ids_arr for {updated_count} positions")
                log_phase_result_fn(9, "populate_trade_ids_arr", "success", f"populated {updated_count} positions")
            else:
                logger.debug("[PHASE 9] All positions have trade_ids_arr populated")
                log_phase_result_fn(9, "populate_trade_ids_arr", "success", "no missing trade_ids_arr")

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        error_msg = f"[PHASE 9 CRITICAL] Failed to populate trade_ids_arr: {e}"
        logger.critical(error_msg)
        log_phase_result_fn(9, "populate_trade_ids_arr", "error", str(e)[:100])
        raise RuntimeError(error_msg) from e


def _sync_position_quantities_step(log_phase_result_fn: Callable[..., Any]) -> None:
    """Backfill algo_trades.quantity from entry_quantity for every live (non-terminal)
    trade whose quantity was never set at all.

    CRITICAL FIX: previously hardcoded `status = 'open'`, which never matches a live
    (execution_mode=auto) filled order - those write status='filled'/'partially_filled'
    literally (see executor_entry_handler.py and the identical fix in exit_engine.py/
    position_monitor.py/exposure_policy.py). Use TradeStatus.all_open() so this sync
    actually covers live positions, not just paper-mode ones.

    BUG FOUND (goal session, "before real money" finance-accuracy audit): this used to
    also re-sync any row where `quantity != entry_quantity`, treating that as "sync
    drift" to correct - but a partial exit legitimately reduces algo_trades.quantity
    below entry_quantity (see executor_exit_handler.py's partial-exit UPDATE), and this
    step runs every single orchestrator cycle. It was silently stomping that correct,
    reduced quantity back up to the full original entry_quantity on the very next run,
    every time - algo/orchestration/position_sync.py then propagated the now-wrong,
    inflated total into algo_positions.quantity too. Live-reproduced via TRD-29F350E6A9
    (RPM): a real partial exit correctly set algo_positions.quantity=11, but by the time
    the final exit ran 2 days later, both algo_trades.quantity and algo_positions.quantity
    read back 22 (the original full size) - in live/auto mode the final exit would have
    submitted a sell order for 11 shares that no longer existed. Scoped to `quantity IS
    NULL` only now - a genuine "this row's quantity was never populated at all" backfill
    (the original migration-1106 problem this function was written for), never a
    legitimately-differing value.
    """
    try:
        open_statuses = TradeStatus.all_open()
        status_placeholders = ", ".join(["%s"] * len(open_statuses))
        with DatabaseContext("write") as cur:
            # ISSUE 12 FIX: Pre-update validation - ensure entry_quantity is valid
            cur.execute(
                f"""
                SELECT COUNT(*) as invalid_count, STRING_AGG(DISTINCT trade_id::text, ',') as trade_ids
                FROM algo_trades
                WHERE status IN ({status_placeholders})
                  AND quantity IS NULL
                  AND (entry_quantity IS NULL OR entry_quantity <= 0)
                """,
                tuple(open_statuses),
            )
            validation = cur.fetchone()
            invalid_count = validation[0] if validation else 0
            if invalid_count and invalid_count > 0:
                invalid_trades = validation[1] if len(validation) > 1 else "unknown"
                logger.error(
                    f"[PHASE 9] Cannot sync position quantities: {invalid_count} open trade(s) have invalid entry_quantity "
                    f"(NULL or <= 0): {invalid_trades}. Data integrity issue detected."
                )
                raise ValueError(
                    f"Position quantity sync aborted: {invalid_count} trades have invalid entry_quantity. "
                    f"Cannot proceed with sync when source data is corrupted."
                )

            cur.execute(
                f"""
                UPDATE algo_trades
                SET quantity = entry_quantity, updated_at = CURRENT_TIMESTAMP
                WHERE status IN ({status_placeholders}) AND quantity IS NULL
                """,
                tuple(open_statuses),
            )
            synced_count = cur.rowcount

            # ISSUE 12 FIX: Verify the update actually worked
            if synced_count > 0:
                cur.execute(
                    f"""
                    SELECT trade_id, quantity, entry_quantity
                    FROM algo_trades
                    WHERE status IN ({status_placeholders})
                      AND quantity IS NULL
                    LIMIT 10
                    """,
                    tuple(open_statuses),
                )
                mismatches = cur.fetchall()

                if mismatches:
                    logger.critical(
                        f"[PHASE 9] Position quantity sync verification FAILED: {len(mismatches)} rows still NULL. "
                        f"UPDATE statement did not properly backfill quantities."
                    )
                    for trade_id, qty, entry_qty in mismatches[:5]:
                        logger.error(f"  Trade {trade_id}: quantity={qty}, entry_quantity={entry_qty} (expected set)")
                    raise RuntimeError(
                        f"Position quantity sync verification failed: {len(mismatches)} trades still have NULL quantity "
                        f"after UPDATE. Database may be in an inconsistent state."
                    )

                logger.info(f"[PHASE 9] Backfilled quantity for {synced_count} open positions (was NULL)")
                logger.info(f"[PHASE 9] Verification PASSED: All {synced_count} positions backfilled correctly")
            else:
                logger.debug("[PHASE 9] No quantity backfill needed - all open positions have quantity set")
        log_phase_result_fn(
            9,
            "quantity_sync",
            "success",
            f"synced {synced_count} open positions" if synced_count > 0 else "no sync needed",
        )
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[PHASE 9] CRITICAL: Failed to sync quantity column: {e}")
        log_phase_result_fn(9, "quantity_sync", "error", f"sync failed: {str(e)[:60]}")
    except (ValueError, RuntimeError) as e:
        logger.error(f"[PHASE 9] CRITICAL: Position quantity sync validation failed: {e}")
        log_phase_result_fn(9, "quantity_sync", "error", f"validation failed: {str(e)[:60]}")


def _refresh_positions_with_risk_view(log_phase_result_fn: Callable[..., Any]) -> None:
    """Refresh the algo_positions_with_risk materialized view so the dashboard reflects
    current state after reconciliation updates algo_positions from the broker.

    CRITICAL FIX: a permission-denied error is only expected when actually running in
    LOCAL_MODE (the local dev DB role isn't a superuser and can't refresh materialized
    views). Previously this treated ANY InsufficientPrivilege as that expected local
    case unconditionally, so a real production misconfiguration - e.g. the DB role
    losing REFRESH privilege after a credential rotation, or a migration applied under
    the wrong role - would silently downgrade to a warning forever, leaving the
    positions/risk dashboard serving stale data with no critical alert ever firing.
    """
    try:
        with DatabaseContext("write") as cur:
            cur.execute("REFRESH MATERIALIZED VIEW algo_positions_with_risk")
        logger.info("[PHASE 9] Refreshed algo_positions_with_risk materialized view")
        log_phase_result_fn(
            9,
            "positions_view_refresh",
            "success",
            "algo_positions_with_risk refreshed",
        )
    except psycopg2.errors.InsufficientPrivilege as e:
        local_mode = os.getenv("LOCAL_MODE", "").lower() in ("1", "true", "yes")
        if local_mode:
            # Permission denied is expected in LOCAL_MODE (non-superuser cannot refresh materialized views)
            # This is not a critical failure - just log warning and continue
            logger.warning(
                "[PHASE 9] Cannot refresh algo_positions_with_risk (permission denied - expected in LOCAL_MODE). "
                "View will use cached data; next proper execution with elevated privileges will refresh it."
            )
            log_phase_result_fn(
                9,
                "positions_view_refresh",
                "warning",
                "skipped (permission denied - expected in LOCAL_MODE)",
            )
        else:
            # Outside LOCAL_MODE this means the DB role lost REFRESH privilege on the
            # view (e.g. a credential rotation or migration ran as the wrong role) -
            # a real misconfiguration, not an expected condition. Treat as critical
            # like other view-refresh failures instead of silently downgrading forever.
            error_msg = (
                f"[PHASE 9 CRITICAL] Failed to refresh algo_positions_with_risk materialized view: "
                f"permission denied ({e}). Dashboard position data will become stale. "
                f"Fix: GRANT REFRESH ON MATERIALIZED VIEW algo_positions_with_risk TO <db_role>; "
                f"or run as superuser with elevated privileges. "
                f"Check: (1) DB role has REFRESH grant on view, (2) connection using correct DB role"
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg) from e
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # Other DB errors are critical (disk space, connection issues, view corruption)
        error_msg = (
            f"[PHASE 9 CRITICAL] Failed to refresh algo_positions_with_risk materialized view: {e}. "
            f"Dashboard position data will become stale. "
            f"Check: (1) materialized view definition, (2) database disk space"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg) from e


def _repair_missing_exit_prices(log_phase_result_fn: Callable[..., Any]) -> None:
    """CRITICAL FIX 2026-08-08: Detect and repair trades with exit_date set but exit_price NULL.

    This is a data corruption scenario from Phase 9 reconciliation runs where the UPDATE statement
    ran but exit_price didn't get persisted (see _record_closed_positions_exits comments).
    Trades in this state have:
    - exit_date: populated (not NULL)
    - exit_reason: populated (says "Closed position recorded during reconciliation")
    - profit_loss_dollars: populated (but based on missing exit_price, likely 0.00)
    - exit_price: NULL (MISSING - the bug!)
    - status: 'open' (should be 'closed' if exit was recorded)

    This function finds such trades and recovers the exit_price from price_daily or broker fills.
    """
    try:
        with DatabaseContext("read") as cursor:
            # BUG FOUND 2026-08-25 (real-money-readiness goal session, sweep for the same bug
            # class as phase1_data_freshness.py's orphaned-position fix): the hand-rolled
            # ('open', 'filled', 'partially_filled') list omitted 'active'/'pending'/
            # 'paper_pending' from TradeStatus.all_open() - a corrupted trade left in one of
            # those statuses by the exact partial/buggy exit-write this function exists to
            # detect would silently never surface here. Use TradeStatus.all_open() directly.
            cursor.execute(
                """
                SELECT trade_id, symbol, entry_price, exit_date,
                       profit_loss_dollars, stop_loss_price, entry_quantity
                FROM algo_trades
                WHERE exit_date IS NOT NULL
                  AND exit_price IS NULL
                  AND exit_reason ILIKE '%Closed position recorded during reconciliation%'
                  AND status = ANY(%s)
                ORDER BY exit_date DESC
                LIMIT 100
                """,
                (list(TradeStatus.all_open()),),
            )
            corrupted = cursor.fetchall()

        if not corrupted:
            logger.info("[PHASE 9] No corrupted trades found with missing exit_price")
            return

        logger.warning(
            f"[PHASE 9 CRITICAL] Found {len(corrupted)} trades with corrupted exit data "
            f"(exit_date set but exit_price NULL). Attempting recovery..."
        )

        fixed_count = 0
        with DatabaseContext("write") as cursor:
            for row in corrupted:
                trade_id, symbol, entry_price, exit_date, _, stop_price, entry_qty = row
                if entry_price is None or stop_price is None or entry_qty is None:
                    logger.warning(
                        f"[PHASE 9] Cannot repair {symbol} (trade_id={trade_id}): "
                        f"missing required fields (entry_price={entry_price}, stop_price={stop_price}, entry_qty={entry_qty})"
                    )
                    continue

                # BUG FOUND 2026-08-10 (NaN-comparison-guard class, inverted variant): the
                # `pnl_pct_corrected` guard below reads `if entry_price != 0 else 0.0` -
                # `!=` is TRUE for NaN against everything including 0 (NaN != 0 is True in
                # Python), so a NaN entry_price would sail straight past that "protection"
                # into a real division, writing a NaN profit_loss_pct for a real trade via
                # the UPDATE below. Postgres numeric/float columns can genuinely store NaN.
                # Validate here, matching this same function's own recovered_exit_price
                # guard a few lines down, before entry_price/stop_price/entry_qty are used
                # in any arithmetic.
                entry_price_f = float(entry_price)
                stop_price_f = float(stop_price)
                entry_qty_f = float(entry_qty)
                if (
                    math.isnan(entry_price_f)
                    or math.isinf(entry_price_f)
                    or math.isnan(stop_price_f)
                    or math.isinf(stop_price_f)
                    or math.isnan(entry_qty_f)
                    or math.isinf(entry_qty_f)
                ):
                    logger.warning(
                        f"[PHASE 9] Cannot repair {symbol} (trade_id={trade_id}): "
                        f"non-finite required field (entry_price={entry_price_f}, "
                        f"stop_price={stop_price_f}, entry_qty={entry_qty_f})"
                    )
                    continue

                # Try to recover exit_price from price_daily
                cursor.execute(
                    """
                    SELECT close FROM price_daily
                    WHERE symbol = %s AND date = %s AND (data_unavailable IS NOT TRUE)
                    LIMIT 1
                """,
                    (symbol, exit_date),
                )
                price_row = cursor.fetchone()

                if price_row is None or price_row[0] is None:
                    logger.warning(
                        f"[PHASE 9] Cannot repair {symbol} (trade_id={trade_id}): "
                        f"no price_daily close available for {exit_date}"
                    )
                    continue

                recovered_exit_price = float(price_row[0])
                # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `<= 0` never catches NaN -
                # this feeds real P&L/exit_price writes in the corrupted-trade repair routine.
                if math.isnan(recovered_exit_price) or math.isinf(recovered_exit_price) or recovered_exit_price <= 0:
                    logger.warning(
                        f"[PHASE 9] Cannot repair {symbol} (trade_id={trade_id}): "
                        f"recovered exit_price {recovered_exit_price} is invalid (must be > 0)"
                    )
                    continue

                # Recalculate P&L based on recovered exit_price
                pnl_per_share = recovered_exit_price - float(entry_price)
                pnl_dollars_corrected = float(pnl_per_share * float(entry_qty))
                pnl_pct_corrected = float((pnl_per_share / float(entry_price)) * 100) if entry_price != 0 else 0.0

                risk_per_share = float(entry_price) - float(stop_price)
                if risk_per_share > 0:
                    r_multiple = pnl_per_share / risk_per_share
                else:
                    r_multiple = 0.0

                # Update the trade with recovered exit_price
                cursor.execute(
                    """
                    UPDATE algo_trades
                    SET exit_price = %s::numeric,
                        profit_loss_dollars = %s,
                        profit_loss_pct = %s,
                        exit_r_multiple = %s,
                        reconciliation_note = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE trade_id = %s
                """,
                    (
                        Decimal(str(recovered_exit_price)),
                        pnl_dollars_corrected,
                        pnl_pct_corrected,
                        r_multiple,
                        f"REPAIRED: exit_price recovered from price_daily EOD close {exit_date} "
                        f"(original was NULL despite exit_date being set)",
                        trade_id,
                    ),
                )

                if cursor.rowcount > 0:
                    logger.info(
                        f"[PHASE 9 REPAIR] {symbol} (trade_id={trade_id}): "
                        f"recovered exit_price ${recovered_exit_price:.2f}, "
                        f"corrected P&L ${pnl_dollars_corrected:+.2f}"
                    )
                    fixed_count += 1

        if fixed_count > 0:
            logger.info(f"[PHASE 9] Repaired {fixed_count} corrupted trades with missing exit_price")
            log_phase_result_fn(
                9, "repair_missing_exit_prices", "success", f"repaired {fixed_count} trades with recovered exit prices"
            )
        else:
            logger.info("[PHASE 9] No trades could be repaired (missing price_daily data)")

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[PHASE 9] Repair of missing exit prices failed: {e}")
        log_phase_result_fn(9, "repair_missing_exit_prices", "warn", f"repair failed: {str(e)[:100]}")


def _record_closed_positions_exits(  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
    config: Any,
    run_date: _date,
    log_phase_result_fn: Callable[..., Any],
) -> None:
    """Record exits for recently closed positions.

    This is a catch-up pass for positions closed WITHOUT algo_trades being updated in the
    same transaction (e.g. a broker-side close detected only during reconciliation) - the
    normal exit_engine.py -> executor_exit_handler.py path already updates algo_trades
    (exit_date, exit_price, profit_loss_dollars, status='closed') in the same transaction
    as the algo_positions close, so those positions must never reach this function's
    UPDATE, which assumes exactly one still-open (exit_date IS NULL) algo_trades row.

    CRITICAL FIX 2026-07-29: the SELECT was using algo_positions.current_price (a stale
    market quote, not a confirmed broker fill). When current_price wasn't refreshed after
    the position closed at the broker, it silently equaled entry_price, fabricating $0.00
    P&L that hid real gains/losses and corrupted portfolio metrics. Now fetches actual
    Alpaca fill prices for every closed order (reconcile_exit_fills pattern), and only
    falls back to price_daily EOD closes if broker data unavailable. This ensures every
    closed position's P&L is calculated from ACTUAL execution prices, not stale quotes.

    CRITICAL FIX (earlier): the SELECT below previously had no such filter - it picked up EVERY
    position closed today regardless of whether algo_trades was already updated, so this
    function crashed on any position that had already closed correctly through the normal
    exit_engine path (the ordinary, everyday case for every stop-loss/target exit), not
    just genuinely orphaned ones. Live-reproduced 2026-07-27: 9 positions closed normally
    via exit_engine.py (algo_trades.exit_date already set) still matched this SELECT, and
    the first one processed (LPG) then failed the UPDATE's `exit_date IS NULL` match with
    "0 rows affected", raising a false "data integrity issue" and halting all trading -
    on a day where every exit had in fact been recorded correctly.
    """
    from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter

    try:
        # Fetch actual broker exit prices for any closed sells
        broker_exit_prices = {}  # symbol -> {exit_price, fill_qty}
        try:
            # CRITICAL FIX: this read os.getenv("EXECUTION_MODE") - a variable never set
            # anywhere in deployment (terraform/lambda both set ORCHESTRATOR_EXECUTION_MODE;
            # "EXECUTION_MODE" is documented in environment_validation.py as a legacy ALIAS
            # name, not something actually exported). execution_mode always resolved to ""
            # here, so this broker-fetch block - specifically added so closed-position P&L
            # uses ACTUAL Alpaca fill prices instead of stale price_daily EOD closes - never
            # ran, in paper, dry, review, OR real live/auto mode. Every other execution_mode
            # check in this same file (and orchestrator.py's own comment: "the DB value is
            # what actually governs") reads config.get("execution_mode") - match that here.
            execution_mode = config.get("execution_mode")
            if execution_mode == "auto":
                broker = AlpacaBrokerAdapter({})
                orders = broker.fetch_closed_orders(since=run_date - timedelta(days=2))
                if orders:
                    for order in orders:
                        if order.get("status") == "filled" and order.get("side") == "sell":
                            symbol = order.get("symbol")
                            filled_price_str = order.get("filled_avg_price")
                            filled_qty_str = order.get("filled_qty")
                            if symbol and filled_price_str and filled_qty_str:
                                try:
                                    filled_price = float(filled_price_str)
                                    filled_qty = float(filled_qty_str)
                                    if filled_price > 0 and filled_qty > 0:
                                        broker_exit_prices[symbol] = {
                                            "exit_price": filled_price,
                                            "filled_qty": filled_qty,
                                        }
                                except (ValueError, TypeError) as parse_err:
                                    # Narrow enrichment skip, not a correctness gap: this symbol
                                    # just falls back to price_daily EOD close (the pre-existing
                                    # default) instead of the exact broker fill price. Logged at
                                    # debug (not silent) so a run of malformed broker records is
                                    # still visible without being alert-worthy on its own.
                                    logger.debug(
                                        f"[PHASE 9] Skipping malformed broker order for {symbol}: "
                                        f"filled_avg_price={filled_price_str!r}, filled_qty={filled_qty_str!r} "
                                        f"({parse_err})"
                                    )
        except Exception as broker_err:
            logger.warning(
                f"[PHASE 9] Could not fetch broker fills for exit reconciliation: {broker_err}. "
                f"Will fall back to price_daily EOD closes."
            )

        with DatabaseContext("read") as cursor:
            from utils.trading.status import TradeStatus

            open_trade_statuses = TradeStatus.all_open()
            cursor.execute(
                """
                SELECT ap.symbol, ap.avg_entry_price, ap.quantity, at.stop_loss_price, at.entry_quantity, at.trade_id AS exit_trade_id, ap.current_price, ap.position_id
                FROM algo_positions ap
                CROSS JOIN LATERAL UNNEST(ap.trade_ids_arr) AS unnested_trade_id
                JOIN algo_trades at ON at.trade_id::text = unnested_trade_id::text
                WHERE ap.status = 'closed' AND ap.closed_at::date = %s
                  AND at.exit_date IS NULL
                  AND at.status = ANY(%s)
                  AND (ap.exit_reason IS NULL OR ap.exit_reason NOT ILIKE 'CLEANUP%%')
                  AND ap.created_at < NOW() - INTERVAL '60 seconds'
                ORDER BY ap.closed_at DESC
            """,
                (run_date, list(open_trade_statuses)),
            )
            closed_positions = cursor.fetchall()

        if closed_positions:
            exits_recorded = 0
            # BUG FOUND 2026-09-07 (real-money-readiness audit): the CROSS JOIN LATERAL
            # UNNEST(ap.trade_ids_arr) query above yields one row per still-untouched leg of a
            # pyramided position (2+ algo_trades rows sharing one algo_positions row). The
            # prior_partial_pnl lookup a few hundred lines below is scoped only by
            # symbol+action_date, not by trade_id/position - so every leg of the SAME position
            # processed in this same batch re-queries and re-adds the identical prior partial
            # P&L into that leg's OWN profit_loss_dollars. Summing profit_loss_dollars across a
            # position's algo_trades rows (the natural way to get total realized P&L) then
            # double/triple-counts the prior partial exactly N times for an N-leg position.
            # Track which position_ids have already been credited with their prior partial P&L
            # in this batch and zero it out for every subsequent leg of the same position.
            positions_credited_partial_pnl: set[Any] = set()
            with DatabaseContext("write") as write_cursor:
                acquire_advisory_lock(write_cursor, ALGO_TRADES_LOCK_ID, "algo_trades")
                acquire_advisory_lock(write_cursor, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                try:
                    for row in closed_positions:
                        if not isinstance(row, (tuple, list)) or len(row) < 8:
                            logger.error(
                                f"[PHASE 9] Malformed row from closed_positions query: {row} (type={type(row).__name__}, len={len(row) if isinstance(row, (tuple, list)) else 'N/A'})"
                            )
                            raise RuntimeError(
                                f"[PHASE 9 CRITICAL] Malformed closed position row returned from database. Expected 8 columns, got {len(row) if isinstance(row, (tuple, list)) else '?'}"
                            )
                        try:
                            (
                                symbol,
                                entry_price,
                                position_qty,
                                stop_loss_price,
                                entry_qty,
                                trade_id,
                                current_price,
                                position_id,
                            ) = row
                        except (ValueError, TypeError) as unpack_err:
                            logger.error(f"[PHASE 9] Failed to unpack row: {row}. Error: {unpack_err}")
                            raise RuntimeError(
                                f"[PHASE 9 CRITICAL] Failed to unpack database row: {unpack_err}. Row: {row}"
                            ) from unpack_err

                        if entry_price is None or entry_price <= 0:
                            error_msg = (
                                f"[PHASE 9 CRITICAL] Trade {symbol} has invalid entry_price ({entry_price}). "
                                f"Cannot record trade P&L without valid entry price. "
                                f"This indicates a position tracking or database corruption issue. "
                                f"Halting Phase 9 to prevent audit trail corruption."
                            )
                            logger.critical(error_msg)
                            raise RuntimeError(error_msg)

                        # BUG FOUND 2026-08-31: unlike algo_positions.stop_loss_price (NOT NULL since
                        # migration 020), algo_trades.stop_loss_price has no such constraint - other
                        # code in this same file (see the WHERE stop_loss_price IS NOT NULL filters
                        # elsewhere) already treats it as nullable in practice. Without this guard, a
                        # NULL here reaches `float(entry_price) - float(stop_loss_price)` below and
                        # raises an uncaught TypeError - not a psycopg2 error, so it isn't caught by
                        # this function's `except (psycopg2.DatabaseError, psycopg2.OperationalError)`
                        # handlers, and it occurs before the per-symbol SAVEPOINT even exists. It
                        # propagates out of the whole `with DatabaseContext("write")` block, which
                        # rolls back on ANY exception - silently discarding every other symbol already
                        # successfully recorded earlier in this same batch, not just this one row.
                        if position_qty is None or position_qty <= 0:
                            error_msg = (
                                f"[PHASE 9 CRITICAL] Trade {symbol} has invalid position_qty ({position_qty}). "
                                f"Cannot record trade P&L without a valid closed quantity. "
                                f"Halting Phase 9 to prevent audit trail corruption."
                            )
                            logger.critical(error_msg)
                            raise RuntimeError(error_msg)
                        if entry_qty is None or entry_qty <= 0:
                            error_msg = (
                                f"[PHASE 9 CRITICAL] Trade {symbol} (trade_id={trade_id}) has invalid "
                                f"entry_quantity ({entry_qty}) on algo_trades. Cannot calculate this leg's "
                                f"P&L without its own share count. Halting Phase 9 to prevent audit trail "
                                f"corruption."
                            )
                            logger.critical(error_msg)
                            raise RuntimeError(error_msg)
                        if stop_loss_price is None:
                            error_msg = (
                                f"[PHASE 9 CRITICAL] Trade {symbol} (trade_id={trade_id}) has NULL "
                                f"stop_loss_price on algo_trades. Cannot calculate risk_per_share/R-multiple. "
                                f"Halting Phase 9 to prevent audit trail corruption - backfill "
                                f"algo_trades.stop_loss_price for this trade_id before re-running."
                            )
                            logger.critical(error_msg)
                            raise RuntimeError(error_msg)

                        # CRITICAL FIX 2026-07-29: Fetch actual exit price from broker or price_daily,
                        # NOT from stale algo_positions.current_price. Use reconciliation pattern from
                        # reconciliation.py::resolve_local_pending_exits (use actual price_daily close)
                        # or reconcile_exit_fills (use actual broker fill prices).
                        exit_price = None
                        price_source = None

                        # First priority: actual broker fill price (if available)
                        if symbol in broker_exit_prices:
                            exit_price = broker_exit_prices[symbol]["exit_price"]
                            price_source = "broker fill (from closed_orders)"

                        # Second priority: price_daily EOD close for exit_date
                        if exit_price is None:
                            write_cursor.execute(
                                """
                                SELECT close FROM price_daily
                                WHERE symbol = %s AND date = %s AND (data_unavailable IS NOT TRUE)
                                """,
                                (symbol, run_date),
                            )
                            price_row = write_cursor.fetchone()
                            if price_row is not None and price_row[0] is not None:
                                exit_price = float(price_row[0])
                                price_source = "price_daily EOD close"

                        # Third priority: position's current_price (fallback for intraday closes before EOD price_daily loads)
                        if exit_price is None and current_price is not None and current_price > 0:
                            exit_price = float(current_price)
                            price_source = "position current_price (price_daily not yet loaded for today)"
                            logger.info(
                                f"[PHASE 9] {symbol}: Using position current_price ${exit_price:.2f} "
                                f"(price_daily EOD not available for {run_date})"
                            )

                        # Final fallback: only if NO other price available, mark as estimated pending reconciliation
                        if exit_price is None:
                            raise RuntimeError(
                                f"[PHASE 9 CRITICAL] Exit price for {symbol} position closed {run_date}: "
                                f"No broker fill, price_daily close, or position current_price available. "
                                f"Cannot calculate P&L without actual execution price. "
                                f"Halting Phase 9 to prevent fake P&L records."
                            )

                        # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `<= 0` never
                        # catches NaN. The price_daily-EOD-close fallback path above (line ~1410)
                        # has no earlier `> 0` filter before assignment (unlike the broker-fill
                        # priority, which happens to filter via an upstream check) - this is the
                        # real gate before writing exit_price/P&L for a closed position.
                        if math.isnan(exit_price) or math.isinf(exit_price) or exit_price <= 0:
                            raise ValueError(
                                f"[PHASE 9 CRITICAL] Exit price {exit_price} for {symbol} is invalid (must be > 0). "
                                f"Price source: {price_source}. Cannot record exit with invalid price."
                            )
                        # Calculate actual P&L using real exit_price (not estimated/NULL)
                        risk_per_share = float(entry_price) - float(stop_loss_price)
                        if math.isnan(risk_per_share) or math.isinf(risk_per_share) or risk_per_share <= 0:
                            raise ValueError(
                                f"[PHASE 9 CRITICAL] {symbol}: Invalid risk_per_share={risk_per_share}. "
                                f"Stop loss ({stop_loss_price}) >= entry price ({entry_price}). "
                                f"Cannot calculate R-multiple with corrupted stop price."
                            )

                        # P&L on THIS TRADE LEG's own share count (entry_qty), not the position's
                        # aggregate quantity. BUG FOUND 2026-09-06 (real-money-readiness audit): a
                        # pyramided position (built from 2+ entries, one algo_trades row per entry,
                        # all sharing algo_positions.trade_ids_arr) unnests to one row per trade_id
                        # here, and every row shares the SAME ap.quantity (the position's full
                        # aggregate size). Using position_qty as the per-leg multiplier wrote the
                        # full aggregate P&L into EACH leg's algo_trades row instead of that leg's
                        # own slice of it, overstating total recorded realized P&L roughly Nx for
                        # this catch-up path (fires when the normal exit-recording flow was bypassed
                        # by a broker-side close). entry_qty is correct here specifically because
                        # this branch is scoped to `at.exit_date IS NULL` - a leg that already had a
                        # partial exit recorded through the normal path would have exit_date set and
                        # be excluded, so an untouched leg's full entry_quantity is still open.
                        pnl_per_share_dec = Decimal(str(exit_price)) - Decimal(str(entry_price))
                        pnl_dollars_dec = (pnl_per_share_dec * Decimal(str(entry_qty))).quantize(
                            Decimal("0.01"), ROUND_HALF_UP
                        )
                        pnl_pct_dec = (pnl_per_share_dec / Decimal(str(entry_price)) * Decimal(100)).quantize(
                            Decimal("0.01"), ROUND_HALF_UP
                        )
                        r_multiple_dec = (pnl_per_share_dec / Decimal(str(risk_per_share))).quantize(
                            Decimal("0.01"), ROUND_HALF_UP
                        )

                        # Check for any prior partial exits to compute cumulative P&L (same fix as executor_exit_handler).
                        # Only credit this once per position (see positions_credited_partial_pnl comment
                        # above the loop) - every subsequent leg of the same pyramided position gets 0
                        # here so the prior partial isn't re-added into every leg's own P&L row.
                        if position_id is not None and position_id in positions_credited_partial_pnl:
                            prior_partial_pnl = Decimal(0)
                        else:
                            write_cursor.execute(
                                """
                                SELECT COALESCE(SUM((details->>'pnl_dollars')::numeric), 0)
                                FROM algo_audit_log
                                WHERE action_type LIKE 'exit_%%'
                                  AND symbol = %s
                                  AND action_date::date = %s
                                  AND (details->>'full_exit')::boolean = false
                                """,
                                (symbol, run_date),
                            )
                            prior_partial = write_cursor.fetchone()
                            if prior_partial and len(prior_partial) > 0 and prior_partial[0] is not None:
                                prior_partial_pnl = Decimal(str(prior_partial[0]))
                            else:
                                prior_partial_pnl = Decimal(0)
                            if position_id is not None:
                                positions_credited_partial_pnl.add(position_id)

                        # Cumulative P&L across all legs
                        cumulative_pnl_dollars = float(
                            (prior_partial_pnl + pnl_dollars_dec).quantize(Decimal("0.01"), ROUND_HALF_UP)
                        )
                        # FIXED 2026-09-07 (same bug class/fix as executor_exit_handler.py's
                        # _compute_cumulative_pnl - see 8e0c0ccec/4735a8bc4 - THIRD independent
                        # copy of this logic found by grepping for "cumulative_pnl" repo-wide):
                        # entry_qty here is this ONE leg's own entry_quantity (correct for
                        # pnl_dollars_dec above, since this branch is scoped to untouched legs -
                        # see the comment above pnl_per_share_dec) but understates the true cost
                        # basis/risk denominator when prior_partial_pnl != 0 - i.e. this position
                        # is BOTH pyramided (2+ legs) AND was exited via multiple partial legs.
                        # Sum entry_quantity across every leg on the position instead of trusting
                        # this one row's own quantity, same trade_ids_arr sum as the other two
                        # fixes.
                        total_entry_qty = entry_qty
                        if prior_partial_pnl != 0 and position_id is not None:
                            write_cursor.execute(
                                """
                                SELECT SUM(t2.entry_quantity)
                                FROM algo_trades t2
                                JOIN algo_positions p2 ON t2.trade_id::text = ANY(p2.trade_ids_arr::text[])
                                WHERE p2.position_id = %s
                                """,
                                (position_id,),
                            )
                            total_entry_qty_row = write_cursor.fetchone()
                            if total_entry_qty_row and total_entry_qty_row[0] is not None:
                                total_entry_qty = total_entry_qty_row[0]
                        cumulative_pnl_pct = (
                            float(pnl_pct_dec)
                            if prior_partial_pnl == 0
                            else float(
                                (
                                    Decimal(str(cumulative_pnl_dollars))
                                    / (Decimal(str(entry_price)) * Decimal(str(total_entry_qty)))
                                    * Decimal(100)
                                ).quantize(Decimal("0.01"), ROUND_HALF_UP)
                            )
                        )
                        cumulative_r_multiple = (
                            float(r_multiple_dec)
                            if prior_partial_pnl == 0
                            else float(
                                (
                                    Decimal(str(cumulative_pnl_dollars))
                                    / (Decimal(str(risk_per_share)) * Decimal(str(total_entry_qty)))
                                ).quantize(Decimal("0.01"), ROUND_HALF_UP)
                            )
                        )

                        # CRITICAL FIX 2026-07-30: Validate P&L calculations before update
                        # Recent audit found profit_loss_pct=NULL on some closed trades
                        if cumulative_pnl_pct is None or not isinstance(cumulative_pnl_pct, (int, float)):
                            raise ValueError(
                                f"[PHASE 9 CRITICAL] P&L calculation error for {symbol}: "
                                f"cumulative_pnl_pct={cumulative_pnl_pct} (type={type(cumulative_pnl_pct)}). "
                                f"Cannot update trade with NULL/invalid profit_loss_pct. "
                                f"Check: entry_price={entry_price}, exit_price={exit_price}, "
                                f"position_qty={position_qty}, entry_qty={entry_qty}, "
                                f"risk_per_share={risk_per_share}"
                            )

                        sp = f"sp_exit_{symbol.replace('-', '_').replace('.', '_')}"
                        try:
                            from utils.trading.status import TradeStatus

                            open_trade_statuses_2 = TradeStatus.all_open()
                            trade_status_ph_2 = ", ".join(["%s"] * len(open_trade_statuses_2))
                            write_cursor.execute(f"SAVEPOINT {sp}")

                            # CRITICAL FIX 2026-08-08: Cast exit_price explicitly to numeric to prevent NULL binding
                            # Some trades (IBEX, DAC) had all fields updated EXCEPT exit_price stayed NULL.
                            # This suggests either a parameter binding issue or PostgreSQL type coercion problem.
                            # Explicitly cast to numeric in SQL to force proper type handling.
                            exit_price_numeric = Decimal(str(exit_price))
                            write_cursor.execute(
                                f"""
                                UPDATE algo_trades
                                SET exit_date = %s, exit_time = CURRENT_TIMESTAMP,
                                    exit_price = %s::numeric, estimated_exit_price = NULL,
                                    profit_loss_dollars = %s, profit_loss_pct = %s, exit_r_multiple = %s,
                                    exit_reason = %s, status = 'closed',
                                    trade_duration_days = %s::date - entry_date,
                                    exit_price_reconciled_at = CURRENT_TIMESTAMP,
                                    reconciliation_note = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE trade_id = %s AND exit_date IS NULL AND status IN ({trade_status_ph_2})
                            """,
                                (
                                    run_date,
                                    exit_price_numeric,
                                    cumulative_pnl_dollars,
                                    cumulative_pnl_pct,
                                    cumulative_r_multiple,
                                    f"Closed position recorded during reconciliation (exit price source: {price_source})",
                                    run_date,
                                    f"Recorded from {price_source} on {run_date} (P&L: ${cumulative_pnl_dollars:.2f}, {cumulative_pnl_pct:+.2f}%, {cumulative_r_multiple:+.2f}R)",
                                    trade_id,
                                    *open_trade_statuses_2,
                                ),
                            )

                            # CRITICAL FIX 2026-08-08: Verify exit_price was actually written
                            # If rowcount > 0 but exit_price is NULL in the database, something silently corrupted the data.
                            # Check immediately and raise if validation fails to prevent silent data corruption.
                            if write_cursor.rowcount > 0:
                                write_cursor.execute(
                                    "SELECT exit_price FROM algo_trades WHERE trade_id = %s",
                                    (trade_id,),
                                )
                                verify_row = write_cursor.fetchone()
                                if verify_row and verify_row[0] is None:
                                    error_msg = (
                                        f"[PHASE 9 CRITICAL DATA CORRUPTION] Trade {symbol} (trade_id={trade_id}) exit_price was NOT written despite successful UPDATE. "
                                        f"All other exit fields were set correctly (exit_date, exit_reason, P/L), but exit_price={verify_row[0]}. "
                                        f"This indicates a database constraint violation, trigger, or type binding bug. "
                                        f"Cannot proceed - halting Phase 9 to prevent audit trail corruption."
                                    )
                                    logger.critical(error_msg)
                                    raise RuntimeError(error_msg)
                                exits_recorded += 1
                                logger.info(
                                    f"[PHASE 9 VERIFICATION] Trade {symbol}: exit_price written correctly (${float(exit_price_numeric):.2f})"
                                )
                            elif write_cursor.rowcount == 0:
                                logger.warning(
                                    f"[PHASE 9] Trade {symbol} (trade_id={trade_id}) exit already recorded. "
                                    f"This can happen if another process updated the trade between our SELECT and UPDATE. "
                                    f"Continuing with position update since trade is already finalized."
                                )
                            # Try to update position, but don't fail if it's already closed
                            # (can happen if the position was closed between SELECT and UPDATE)
                            #
                            # SAFETY (2026-09-06, real-money-readiness audit): scope by position_id
                            # (the true unique key) rather than symbol alone whenever it's available.
                            # algo_positions has no DB-level unique constraint on symbol (only on
                            # position_id) - a symbol-only WHERE here would, in the rare case of two
                            # open positions for the same symbol (a pyramiding/race edge case the
                            # application-level dedup is the only guard against), close/misattribute
                            # whichever row happened to match rather than the specific position this
                            # trade actually belongs to. Falls back to symbol-only only for legacy
                            # trades written before position_id linking existed.
                            if position_id:
                                write_cursor.execute(
                                    """
                                    UPDATE algo_positions
                                    SET status = 'closed', closed_at = CURRENT_TIMESTAMP, current_price = %s,
                                        unrealized_pnl = NULL, profit_loss_dollars = %s, unrealized_pnl_pct = %s,
                                        exit_reason = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE position_id = %s AND status = 'open'
                                """,
                                    (
                                        exit_price,
                                        cumulative_pnl_dollars,
                                        cumulative_pnl_pct,
                                        f"Closed position recorded during reconciliation (from {price_source})",
                                        position_id,
                                    ),
                                )
                            else:
                                logger.warning(
                                    f"[PHASE 9] Trade {symbol} (trade_id={trade_id}) has no position_id - "
                                    "falling back to symbol-scoped position update (legacy trade)."
                                )
                                write_cursor.execute(
                                    """
                                    UPDATE algo_positions
                                    SET status = 'closed', closed_at = CURRENT_TIMESTAMP, current_price = %s,
                                        unrealized_pnl = NULL, profit_loss_dollars = %s, unrealized_pnl_pct = %s,
                                        exit_reason = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE symbol = %s AND status = 'open'
                                """,
                                    (
                                        exit_price,
                                        cumulative_pnl_dollars,
                                        cumulative_pnl_pct,
                                        f"Closed position recorded during reconciliation (from {price_source})",
                                        symbol,
                                    ),
                                )
                            if write_cursor.rowcount == 0:
                                # Position may already be closed (status='closed' in the SELECT but between
                                # SELECT and UPDATE it was already finalized). This is OK - algo_trades
                                # exit was recorded successfully, so just skip the position update.
                                logger.debug(
                                    f"[PHASE 9] Position {symbol} was already finalized (status='closed'), "
                                    f"skipping position update since algo_trades exit was recorded"
                                )
                            write_cursor.execute(f"RELEASE SAVEPOINT {sp}")
                            logger.info(
                                f"Recorded exit: {symbol} {position_qty}sh @ ${exit_price:.2f} ({price_source}) on {run_date} "
                                f"- P&L: ${cumulative_pnl_dollars:+.2f} ({cumulative_pnl_pct:+.2f}%, {cumulative_r_multiple:+.2f}R)"
                            )
                        except (
                            psycopg2.DatabaseError,
                            psycopg2.OperationalError,
                        ) as e:
                            # Wrap savepoint rollback in try-except per transaction_abort safety rule
                            try:
                                write_cursor.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                            except psycopg2.Error as rollback_err:
                                logger.error(
                                    f"[PHASE 9] Savepoint rollback failed: {rollback_err}. Original error: {e}"
                                )
                            # CRITICAL: This SELECT is scoped to `closed_at::date = run_date` (see
                            # query above). If this write fails today, the symbol will never be
                            # re-selected by this function on a future run - algo_positions stays
                            # 'closed' while algo_trades.exit_date stays NULL forever, a permanent
                            # audit-trail gap silently invisible to any later reconciliation pass.
                            # That's exactly the outcome this function's other two fail-fast checks
                            # (missing exit_price, invalid entry_price) exist to prevent - so this
                            # must halt too, not just log and move on to the next symbol.
                            error_msg = (
                                f"[PHASE 9 CRITICAL] Failed to record exit for {symbol}: {e}. "
                                f"This position will NEVER be re-selected for exit recording on a "
                                f"future run (query is scoped to today's closed_at date), leaving a "
                                f"permanent audit-trail gap between algo_positions (closed) and "
                                f"algo_trades (still open) unless fixed manually. Halting to prevent "
                                f"silent data corruption per GOVERNANCE (audit trail integrity)."
                            )
                            logger.critical(error_msg)
                            try:
                                from algo.reporting import notify

                                notify(
                                    severity="critical",
                                    title="Phase 9: Exit recording failed - permanent audit gap risk",
                                    message=error_msg,
                                    details={"symbol": symbol, "run_date": str(run_date)},
                                )
                            except (ValueError, TypeError, RuntimeError) as notify_err:
                                logger.error(f"Failed to send exit-recording-failure notification: {notify_err}")
                            raise RuntimeError(error_msg) from e

                    if exits_recorded > 0:
                        logger.info(f"Recorded {exits_recorded} exits in trade history")
                finally:
                    release_advisory_lock(write_cursor, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                    release_advisory_lock(write_cursor, ALGO_TRADES_LOCK_ID, "algo_trades")
        else:
            logger.info("No closed positions found for exit recording")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(
            f"Failed to record exits in trade history: {e}. "
            "Cannot complete reconciliation without persisting trade exit data."
        ) from e


def _cleanup_orphaned_positions(log_phase_result_fn: Callable[..., Any]) -> None:
    """FINDING #6 FIX: Clean up positions with quantity=0 but status='open'.

    These orphaned positions occur when Phase 6 (exit_engine) reduces quantity to 0 but
    fails to update status to 'closed' due to:
    - Concurrent Phase 6 exits in multiple Lambda/ECS tasks (race condition)
    - Transaction rollback after quantity update but before status update
    - Database connection loss mid-update

    This maintenance step runs weekly or on-demand to prevent these orphans from:
    - Blocking risk calculations (they have quantity=0, shouldn't count but do if status='open')
    - Confusing position monitoring (appear open but are actually exited)
    - Skewing performance metrics (cash freed by exit but position still appears open)

    GOVERNANCE: Only closes positions that are truly exited (quantity=0). Validates
    that position truly has zero shares before marking closed. Logs all closures for audit.
    """
    try:
        with DatabaseContext("write") as cur:
            # Find positions with quantity=0 but status='open' (orphaned exits)
            cur.execute(
                """
                SELECT id, symbol, quantity, status, updated_at
                FROM algo_positions
                WHERE quantity = 0 AND status = 'open'
                ORDER BY updated_at DESC
                LIMIT 100
                """
            )
            orphaned_rows = cur.fetchall()

            if not orphaned_rows:
                logger.info("[PHASE 9 MAINTENANCE] No orphaned positions found (quantity=0 with status='open')")
                return

            logger.warning(
                f"[PHASE 9 MAINTENANCE] Found {len(orphaned_rows)} orphaned positions "
                f"(quantity=0 but status='open'). Closing them now..."
            )

            # Close all orphaned positions atomically
            # CRITICAL FIX 2026-08-08: Calculate profit_loss_dollars when closing orphaned positions
            cur.execute(
                """
                UPDATE algo_positions
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP,
                    exit_reason = 'orphan_cleanup|quantity_zero_but_status_open',
                    unrealized_pnl = NULL,
                    profit_loss_dollars = COALESCE(profit_loss_dollars, 0),
                    updated_at = CURRENT_TIMESTAMP
                WHERE quantity = 0 AND status = 'open'
                """
            )
            closed_count = cur.rowcount

            # Log closure details for audit
            for row in orphaned_rows:
                try:
                    pos_id, symbol, qty, status, updated_at = row
                    logger.info(
                        f"[PHASE 9 CLEANUP] Closed orphaned position {pos_id} ({symbol}): "
                        f"quantity={qty}, previous_status={status}, last_updated={updated_at}"
                    )
                except Exception as row_err:
                    logger.warning(f"[PHASE 9 CLEANUP] Failed to unpack orphan row for logging: {row_err}")

            logger.info(f"[PHASE 9 MAINTENANCE] Closed {closed_count} orphaned positions")
            try:
                log_phase_result_fn(
                    9,
                    "orphan_cleanup",
                    "success" if closed_count > 0 else "info",
                    f"cleaned up {closed_count} positions with quantity=0",
                )
            except Exception as log_err:
                logger.warning(f"[PHASE 9] Failed to log orphan cleanup status: {log_err}")

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(
            f"[PHASE 9] Orphan position cleanup failed (non-critical): {e}. "
            "Positions will be retried on next reconciliation run."
        )
        try:
            log_phase_result_fn(9, "orphan_cleanup", "warn", f"failed: {str(e)[:500]}")
        except Exception as log_err:
            logger.warning(f"[PHASE 9] Failed to log orphan cleanup warning: {log_err}")


def _verify_open_position_stop_loss_protection_step(
    log_phase_result_fn: Callable[..., Any], config: Any, sync_positions_first: bool = False
) -> None:
    """Verify every open position still has a live stop-loss leg resting at the broker,
    and auto-repair one that doesn't rather than only alerting a human to do it.

    REAL-MONEY-READINESS FINDING (2026-09-04): entry bracket orders are submitted with
    time_in_force=day (order_manager.py's _build_bracket_order_payload). Whether Alpaca
    expires the OCO stop-loss/take-profit legs at end-of-day once they're live is NOT
    documented either way (checked extensively) - but this strategy holds positions many
    days, and the only existing code that would ever notice a missing leg
    (sync_bracket_stop_loss) only runs REACTIVELY, when position_monitor recommends
    RAISE_STOP. A position that is flat or drawing down - exactly when protection matters
    most - has no trigger that would ever re-check it. This step closes that gap
    regardless of root cause (TIF expiry, manual intervention, a broker-side glitch) by
    proactively checking every open position, every reconciliation cycle.

    UPDATED 2026-09-05 (real-money go-live decision, user-directed): originally
    deliberately detect-and-alert only, on the reasoning that an unconditional
    replace-on-every-check would compound anomalies. That's still true for the
    every-cycle "is a leg live" check itself (unchanged, see check_stop_loss_leg_live's
    own docstring) - but "alert and wait for a human" is not an acceptable real-money
    control when nobody is reliably watching alerts in real time. When a gap is found,
    check_and_repair_one_position (phase9_stop_loss_repair.py) now submits a standalone
    GTC protective stop directly, sized/priced from algo_positions.quantity/
    current_stop_price - the same values exit_engine.py already trusts as the
    position's live truth. The alert is now reserved for cases where the system
    genuinely CANNOT self-heal (the repair submission itself fails) - that is the one
    case that still needs a human.
    """
    try:
        from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager
        from algo.orchestrator.phase9_stop_loss_repair import check_and_repair_one_position
        from algo.trading.order_manager import OrderManager

        sync_mgr = AlpacaSyncManager(config)
        if not sync_mgr.alpaca_key or not sync_mgr.alpaca_secret or not sync_mgr.alpaca_base_url:
            logger.info(
                "[PHASE 9] Stop-loss protection check skipped - no Alpaca credentials/base_url (paper mode, DB-only)."
            )
            log_phase_result_fn(9, "stop_loss_protection_check", "info", "skipped - no Alpaca credentials")
            return

        # REAL-MONEY-READINESS FIX (2026-09-07 pre-live audit): unlike every entry/exit
        # call site in executor.py/executor_entry_handler.py/executor_exit_handler.py,
        # this repair path had NO explicit execution_mode check anywhere - it only gated
        # on credential presence, then handed sync_mgr.alpaca_base_url straight to
        # OrderManager. Today that URL happens to land on the paper endpoint for every
        # non-"auto" mode purely because AlpacaSyncManager.__init__ resolves it via the
        # same create_execution_mode_strategy(...) factory executor.py uses - but that
        # means this repair path's only protection against submitting a real order in
        # "review" mode (documented as "validated but not executed... before automatic
        # execution is enabled") is an implicit URL-resolution side effect, not an
        # explicit gate at THIS call site. One refactor of that shared resolution logic
        # could silently start submitting real repair orders here with nothing catching
        # it. Fail closed instead of trusting the implicit coupling: verify explicitly
        # that a non-"auto" execution_mode actually resolved to the paper endpoint before
        # letting this repair path touch the broker at all.
        execution_mode = str(config.get("execution_mode") or "").lower()
        base_url_is_paper = "paper" in sync_mgr.alpaca_base_url.lower()
        if execution_mode != "auto" and not base_url_is_paper:
            logger.critical(
                f"[PHASE 9 CRITICAL] Stop-loss protection check ABORTED - execution_mode="
                f"'{execution_mode}' but resolved Alpaca base_url does not look like the "
                f"paper endpoint ({sync_mgr.alpaca_base_url}). Refusing to submit repair "
                f"orders in a non-auto mode against what may be a live endpoint."
            )
            log_phase_result_fn(
                9, "stop_loss_protection_check", "error", "aborted - non-auto mode resolved to non-paper endpoint"
            )
            return

        order_mgr = OrderManager(sync_mgr.alpaca_key, sync_mgr.alpaca_secret, sync_mgr.alpaca_base_url)

        # GUARDIAN-MODE FIX (2026-09-06): the normal Phase 9 call path only reaches here
        # AFTER _run_reconciliation_step has already synced algo_positions from live broker
        # fills this cycle (see this file's 2026-09-05 ordering-fix comment above the call
        # site) - a position that legitimately closed reads status='closed' by the time this
        # runs. The standalone stop-loss-guardian Lambda dispatch (lambda_function.py's
        # `mode: "stop_loss_guardian"`) calls straight into this function with NO
        # reconciliation step at all, so between full orchestrator runs algo_positions can
        # sit stale for hours - a position stopped out/take-profited since the last full run
        # still reads status='open' here, has no live stop leg (the bracket that protected it
        # already filled), and would otherwise be treated as a genuine protection gap: either
        # a false "AUTO-REPAIR FAILED - investigate immediately" CRITICAL alert (Alpaca
        # rejects the repair stop for a symbol this long-only account no longer holds) or, on
        # a partial-close, a repair sized off the stale pre-close quantity. Both are exactly
        # the false-alarm bug class the 2026-09-05 ordering fix closed for the main flow -
        # reusing the narrow position-only sync (not the full DailyReconciliation, which also
        # writes a portfolio snapshot/P&L validation this high-frequency schedule must not
        # duplicate) closes the same gap here.
        if sync_positions_first:
            try:
                with DatabaseContext("write") as sync_cur:
                    sync_result = sync_mgr.sync_alpaca_positions(sync_cur)
                logger.info(f"[STOP_LOSS_GUARDIAN] Pre-check position sync: {sync_result.get('message')}")
            except Exception as sync_err:
                logger.critical(
                    f"[STOP_LOSS_GUARDIAN CRITICAL] Position sync before stop-loss check failed, "
                    f"algo_positions may be stale - proceeding with existing DB state: {sync_err}",
                    exc_info=True,
                )

        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT p.id, p.symbol, p.trade_ids_arr, p.quantity, p.current_stop_price,
                       p.standalone_stop_order_id
                FROM algo_positions p
                WHERE p.status = 'open' AND p.quantity > 0
                """
            )
            open_positions = cur.fetchall()

        if not open_positions:
            logger.info("[PHASE 9] No open positions to verify stop-loss protection for.")
            log_phase_result_fn(9, "stop_loss_protection_check", "info", "no open positions")
            return

        checked = 0
        repaired: list[str] = []
        unrepairable: list[str] = []
        check_failures: list[str] = []
        for pos_id, symbol, trade_ids_arr, quantity, current_stop_price, standalone_stop_order_id in open_positions:
            # REAL-MONEY-READINESS FIX (2026-09-05 audit): check_and_repair_one_position
            # issues its own DB reads/writes outside of any try/except (e.g. the
            # alpaca_order_id lookup) - an unhandled exception there used to propagate out
            # of this loop entirely, silently skipping verification of every remaining
            # open position for the rest of this cycle with nothing beyond a warning log
            # at the bottom of this function. One symbol's transient DB hiccup must not be
            # able to starve every other position of its stop-loss protection check.
            try:
                outcome = check_and_repair_one_position(
                    order_mgr, pos_id, symbol, trade_ids_arr, quantity, current_stop_price, standalone_stop_order_id
                )
            except Exception as per_pos_err:
                logger.error(
                    f"[PHASE 9] {symbol} (position {pos_id}): stop-loss protection check raised "
                    f"unexpectedly, treating as unrepairable and continuing to next position: {per_pos_err}",
                    exc_info=True,
                )
                check_failures.append(symbol)
                continue
            if outcome == "skipped":
                continue
            checked += 1
            if outcome == "repaired":
                repaired.append(symbol)
            elif outcome == "unrepairable":
                unrepairable.append(symbol)
        unrepairable = unrepairable + check_failures

        if repaired:
            try:
                from algo.reporting.notifications import notify

                notify(
                    "warning",
                    title="Open Position(s) Auto-Repaired Missing Stop-Loss Protection",
                    message=(
                        f"{len(repaired)} open position(s) had NO live stop-loss leg resting at "
                        f"the broker and were automatically re-protected with a new standalone "
                        f"GTC stop order: {', '.join(repaired)}. No action required, but worth "
                        "reviewing why the original bracket leg went missing."
                    ),
                )
            except Exception as notify_err:
                logger.warning(f"[PHASE 9] Failed to send auto-repair notification for {repaired}: {notify_err}")

        if unrepairable:
            # REAL-MONEY-READINESS FIX (2026-09-05, ported from an unmerged WIP fix found
            # while checking on flagged real-money-readiness gaps): this is the alert of last
            # resort for a position confirmed to have NO stop-loss protection - the exact
            # scenario this whole check was built to catch. It used to call notify() without
            # strict=True, meaning notify()'s own blanket except (notifications.py) would
            # swallow a genuine delivery failure (e.g. SMTP down/misconfigured - the only
            # channel this codebase's notify() actually has, see notifications.py's
            # _send_notification) and this function's own except below could never
            # distinguish "delivered" from "silently failed to deliver" - both looked
            # identical: a log line nobody may ever read. strict=True makes a real delivery
            # failure raise NotificationError instead, which triggers one immediate retry
            # (covers a transient SMTP blip) before falling through to the loudest failure
            # signal available in this function's scope (log_phase_result_fn below still
            # records "critical" phase-result status regardless, so a dashboard/monitoring
            # check of phase results is a second, independent trace of this even if both
            # notify attempts fail outright).
            from algo.reporting.notifications import notify
            from algo.trading.exceptions import NotificationError

            alert_title = "Open Position(s) Missing Stop-Loss Protection - AUTO-REPAIR FAILED"
            alert_message = (
                f"{len(unrepairable)} open position(s) have NO live stop-loss leg AND "
                f"automatic repair failed: {', '.join(unrepairable)}. Do not assume these "
                "positions are protected - investigate and re-arm protection immediately."
            )
            try:
                notify("critical", title=alert_title, message=alert_message, strict=True)
            except NotificationError as first_err:
                logger.critical(
                    f"[PHASE 9 CRITICAL] Alert delivery failed for unrepairable positions "
                    f"{unrepairable} - retrying once: {first_err}"
                )
                try:
                    notify("critical", title=alert_title, message=alert_message, strict=True)
                except NotificationError as retry_err:
                    logger.critical(
                        f"[PHASE 9 CRITICAL] Alert delivery failed TWICE for unrepairable positions "
                        f"{unrepairable} - these positions have NO stop-loss protection and NO ALERT "
                        f"WAS DELIVERED. Manual investigation required immediately: {retry_err}",
                        exc_info=True,
                    )
            except Exception as notify_err:
                logger.critical(
                    f"[PHASE 9 CRITICAL] Failed to alert on unrepairable positions {unrepairable}: {notify_err}",
                    exc_info=True,
                )

        log_phase_result_fn(
            9,
            "stop_loss_protection_check",
            "critical" if unrepairable else ("warn" if repaired else "success"),
            (
                f"{len(repaired)} auto-repaired, {len(unrepairable)} unrepairable "
                f"of {checked} open position(s) checked: repaired={repaired} unrepairable={unrepairable}"
            )
            if (repaired or unrepairable)
            else f"verified {checked} open position(s) protected",
        )

    except Exception as e:
        logger.error(f"[PHASE 9] Stop-loss protection verification step failed unexpectedly: {e}", exc_info=True)
        # REAL-MONEY-READINESS FIX (2026-09-05 audit): a failure of this entire safety-net
        # check (e.g. AlpacaSyncManager init, the open_positions query itself) used to be a
        # log line only - unlike every other failure mode in this function, which pages a
        # human via notify(). The one check whose whole job is catching every other gap
        # must not itself be able to fail silently.
        try:
            from algo.reporting.notifications import notify

            notify(
                "critical",
                title="Stop-Loss Protection Verification Step Failed",
                message=(
                    "Phase 9's per-cycle check that every open position still has a live "
                    f"stop-loss leg at the broker failed to run entirely: {type(e).__name__}: {e}. "
                    "No positions were verified or auto-repaired this cycle - investigate "
                    "immediately, do not assume existing stops are intact."
                ),
            )
        except Exception as notify_err:
            logger.critical(
                f"[PHASE 9 CRITICAL] Failed to alert on stop-loss protection step failure: {notify_err}",
                exc_info=True,
            )
        try:
            log_phase_result_fn(9, "stop_loss_protection_check", "warn", f"check failed: {str(e)[:500]}")
        except Exception:
            pass


def run(  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
    config: Any,
    run_date: _date,
    log_phase_result_fn: Callable[..., Any],
    dry_run: bool = False,
) -> PhaseResult:
    """Execute Phase 9: Reconciliation & Snapshot.

    Args:
        config: Configuration object
        run_date: Date for this run
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status 'ok' if all reconciliation steps succeed. Raises RuntimeError
        (fail-closed, per GOVERNANCE) on any critical step failure rather than returning a
        degraded PhaseResult. All critical reconciliation steps fail-fast to halt trading
        if broker state cannot be verified.
    """
    validate_phase_config(config, "phase_9_reconciliation")

    # MAINTENANCE: Clean up orphaned positions before reconciliation
    # This prevents orphans (quantity=0 but status='open') from skewing metrics
    try:
        _cleanup_orphaned_positions(log_phase_result_fn)
    except Exception as cleanup_err:
        logger.warning(f"[PHASE 9] Orphan cleanup step encountered unexpected error: {cleanup_err}", exc_info=True)
        # Don't halt Phase 9 for cleanup failures - proceed with reconciliation

    # MAINTENANCE: Repair trades with missing exit_price (data corruption from previous runs)
    # This detects trades where exit_date was set but exit_price stayed NULL
    try:
        _repair_missing_exit_prices(log_phase_result_fn)
    except Exception as repair_err:
        logger.warning(f"[PHASE 9] Exit price repair step encountered unexpected error: {repair_err}", exc_info=True)
        # Don't halt Phase 9 for repair failures - proceed with reconciliation

    try:
        from algo.infrastructure.reconciliation import DailyReconciliation

        try:
            recon = DailyReconciliation(config)
        except ValueError as e:
            # GOVERNANCE: Fail-fast on missing Alpaca credentials - no fallback to database state
            # Attempting to reconcile with cached/estimated portfolio values (instead of broker source-of-truth)
            # masks data sync issues and leads to incorrect position sizing on next entry.
            # Better to halt and require explicit credential remediation than to silently degrade.
            if "credentials not found" in str(e).lower() or "credentials" in str(e).lower():
                raise RuntimeError(
                    f"[PHASE 9 CRITICAL] Alpaca credentials not available. "
                    f"Reconciliation requires live broker data. "
                    f"Cannot proceed with trading using stale or estimated portfolio state. "
                    f"Fix: Ensure Alpaca API keys are configured in AWS Secrets Manager (algo/alpaca secret) or environment. "
                    f"Error: {e}"
                ) from e
            else:
                raise RuntimeError(f"[PHASE 9] DailyReconciliation initialization failed: {e}") from e
        reconciliation_succeeded, result = _run_reconciliation_step(config, run_date, log_phase_result_fn, dry_run)

        # SAFETY: Verify every open position still has a live stop-loss leg at the broker.
        # See _verify_open_position_stop_loss_protection_step's docstring for why this exists.
        # Detection-only for the "can't self-heal" case (alerts, never halts Phase 9) - a
        # broker-protection gap that can't auto-repair needs a human to investigate and
        # re-arm, not this reconciliation pass silently placing a new order.
        #
        # ORDERING FIX 2026-09-05 (real-money-readiness audit): this used to run BEFORE
        # _run_reconciliation_step above, querying algo_positions WHERE status='open' while
        # that table could still be stale from the last cycle. A position legitimately
        # stopped out (its bracket's stop-loss leg filled) since then reads as status='open'
        # with a real quantity here, check_stop_loss_leg_live correctly finds no *live* leg
        # (the filled leg isn't live anymore), and phase9_stop_loss_repair.py attempts to
        # auto-repair a position that no longer exists at the broker - Alpaca safely rejects
        # the repair (insufficient qty), but a false "AUTO-REPAIR FAILED... investigate
        # immediately" CRITICAL alert fires for a position that actually exited correctly.
        # Running this AFTER _run_reconciliation_step (which updates status='closed' from
        # real broker fills) means the query below sees the current cycle's fresh state, not
        # last cycle's - closing this false-alarm gap at the source rather than special-
        # casing "no broker position" inside the repair check itself.
        try:
            _verify_open_position_stop_loss_protection_step(log_phase_result_fn, config)
        except Exception as protection_err:
            logger.warning(
                f"[PHASE 9] Stop-loss protection check encountered unexpected error: {protection_err}", exc_info=True
            )
            # Don't halt Phase 9 for this check's own failures - proceed with reconciliation

        # CRITICAL: Validate that local P&L matches Broker P&L
        # Skip if reconciliation failed (recon object may be incomplete or paper mode)
        if reconciliation_succeeded:
            _validate_pnl_step(recon, result, log_phase_result_fn)

        # CRITICAL: Audit for stale estimated exit prices (reconciliation issues)
        # Skip if reconciliation failed (recon object may be incomplete or paper mode)
        if reconciliation_succeeded:
            _audit_exit_prices_step(recon, log_phase_result_fn)

        # Portfolio snapshot is created by DailyReconciliation in reconciliation.py with full metrics
        # Do NOT create a second snapshot here as it would overwrite the proper one with incomplete data
        logger.info(
            f"[PHASE 9] Portfolio snapshot created by DailyReconciliation (reconciliation_succeeded={reconciliation_succeeded})"
        )
        try:
            log_phase_result_fn(9, "portfolio_snapshot", "success", "snapshot created by reconciliation")
        except Exception as snapshot_err:
            logger.warning(f"[PHASE 9 SNAPSHOT] Failed to log snapshot status: {snapshot_err}", exc_info=True)
            log_phase_result_fn(9, "portfolio_snapshot", "warn", f"logging failed: {str(snapshot_err)[:60]}")

        # Record exits for recently closed positions (batch operation to avoid N+1 queries)
        _record_closed_positions_exits(config, run_date, log_phase_result_fn)

        # Step 1: Populate signal_trade_performance from closed trades
        _populate_signal_trade_performance(log_phase_result_fn)

        # Step 2: Generate institutional daily report
        _generate_daily_report(run_date, log_phase_result_fn)

        # Step 3: Compute and log live performance metrics (always run, even on non-trading days)
        # Performance metrics raises explicit RuntimeError/ValueError on critical failures.
        # These must propagate to halt Phase 9 per GOVERNANCE (fail-fast on missing data).
        # Only catch ImportError (optional scipy/numpy dependency).
        try:
            _compute_performance_metrics(config, run_date, log_phase_result_fn)
        except ImportError as e:
            error_msg = (
                f"[PHASE 9] Performance metrics requires scipy/numpy (not available): {e}. "
                f"This is a setup issue, not a data quality issue. "
                f"Install: pip install scipy numpy"
            )
            logger.error(error_msg)
            log_phase_result_fn(9, "performance", "warn", "dependency missing: scipy/numpy")
            # Don't raise - scipy is optional for setup, but if perf metrics fails
            # for data reasons, that WILL be caught and raised above

        # Step 4: Compute and log risk metrics (always run, even on non-trading days)
        # Risk metrics computation MUST succeed - it feeds position sizing and risk limits.
        # Fail-fast per GOVERNANCE if risk data unavailable.
        _compute_risk_metrics(config, run_date, log_phase_result_fn)

        # Step 5: Update algo_metrics_daily with actual trade results from this run
        # Metrics update must persist trade results to audit trail.
        # Fail-fast per GOVERNANCE - audit trail integrity is non-negotiable.
        _update_daily_metrics(run_date, log_phase_result_fn)

        # Populate missing trade_ids_arr for Phase 8-created positions (Session 19 fix).
        # Without this, circuit breaker fails with "orphaned trade_ids_arr" halts.
        _populate_missing_trade_ids_arr(log_phase_result_fn)

        # Sync quantity column for all live trades (entry_quantity -> quantity). Without this,
        # dashboard and risk calculations cannot determine current position sizes.
        _sync_position_quantities_step(log_phase_result_fn)

        # Refresh materialized view so positions dashboard reflects current state.
        # This runs after reconciliation updates algo_positions from Broker.
        _refresh_positions_with_risk_view(log_phase_result_fn)

        # Compute circuit breaker metrics and write to circuit_breaker_status table.
        # Runs after reconciliation so algo_portfolio_snapshots has today's data.
        # dashboard /api/algo/circuit-breakers reads from circuit_breaker_status.
        if reconciliation_succeeded:
            try:
                import psycopg2.extras as _extras

                from loaders.compute_circuit_breakers import compute_circuit_breaker_metrics

                with DatabaseContext("write", cursor_factory=_extras.RealDictCursor) as cb_cur:
                    cb_metrics = compute_circuit_breaker_metrics(cb_cur, today=run_date)
                if cb_metrics is None:
                    raise RuntimeError(
                        f"[PHASE 9 CRITICAL] Circuit breaker metrics computation returned None on {run_date}. "
                        "Cannot proceed with reconciliation without circuit breaker state."
                    )
                triggered = cb_metrics.get("triggered_count")
                any_triggered = cb_metrics.get("any_triggered")
                if triggered is None or any_triggered is None:
                    raise RuntimeError(
                        f"[PHASE 9 CRITICAL] Circuit breaker metrics incomplete on {run_date}: "
                        f"triggered_count={triggered}, any_triggered={any_triggered}. "
                        "Check compute_circuit_breaker_metrics() for data quality issues."
                    )
                logger.info(
                    f"[PHASE 9] Circuit breaker metrics written: {triggered} triggered, any_triggered={any_triggered}"
                )
                log_phase_result_fn(
                    9,
                    "circuit_breaker_metrics",
                    "success",
                    f"{triggered} circuit breakers triggered",
                )
            except Exception as e:
                # CRITICAL: Circuit breaker metrics feed risk dashboards and position limits.
                # Cannot allow stale CB status on dashboard per GOVERNANCE (data integrity).
                error_msg = (
                    f"[PHASE 9 CRITICAL] Circuit breaker metrics computation failed: {e}. "
                    f"Cannot proceed without current risk assessment. "
                    f"Dashboard risk panel will become stale if this phase continues. "
                    f"Check: (1) compute_circuit_breaker_metrics() implementation, "
                    f"(2) circuit_breaker_status table state, (3) database connectivity"
                )
                logger.critical(error_msg)
                raise RuntimeError(error_msg) from e

        # Degrade gracefully if reconciliation failed (e.g., broker unavailable in dry-run)
        # Phase 9 is always_run, so a non-auto-mode failure should not itself halt (see
        # is_governance_halt below for the one case that does).
        is_governance_halt = False
        phase_error: str | None = None
        if reconciliation_succeeded:
            # cash_available/total_return_pct/latest_snapshot: the health dashboard
            # (dashboard/panels/health.py, Phase 9 detail row) already expects these
            # exact keys, but this dict never included them - only portfolio_value made
            # it through, so Cash available/Total return/Last snapshot silently never
            # rendered even though run_daily_reconciliation() now returns the first two
            # (cash_remaining/cumulative_return_pct) and this phase runs immediately
            # after the snapshot write, so "now" is an accurate last-snapshot timestamp.
            data = {
                "portfolio_value": result.get("portfolio_value"),
                "positions": result.get("positions"),
                "unrealized_pnl": result.get("unrealized_pnl"),
                "cash_available": result.get("cash_remaining"),
                "total_return_pct": result.get("cumulative_return_pct"),
                "latest_snapshot": datetime.now(timezone.utc).isoformat(),
                "reconciliation": result,
            }
            phase_status = "ok"
        else:
            # Reconciliation failed - fail-fast (no graceful degradation)
            # GOVERNANCE: Reconciliation is non-negotiable. Using estimated/cached portfolio state
            # instead of broker source-of-truth masks data sync issues and leads to position sizing errors.
            # Better to halt explicitly and require broker access than to silently degrade.
            error_msg = str(result["reason"])

            logger.critical(
                f"[PHASE 9] CRITICAL: Reconciliation failed: {error_msg}. "
                f"Cannot proceed with trading without broker verification of portfolio state. "
                f"Ensure Alpaca API is accessible and credentials are valid."
            )
            phase_status = "error"

            # CRITICAL FIX: this PhaseResult's `halted` field used to be hardcoded False
            # ("Phase 9 is always_run, so it should not cause a halt") below, which was fine
            # for the non-auto DB-fallback path this reasoning was written for, but
            # run_daily_reconciliation()'s broker-connected path (execution_mode="auto", real
            # money) wraps genuinely critical checks - negative broker cash, corrupted account
            # state, missing account fields - in a broad except that turns them into this same
            # success=False/"error" result. Live-reproduced: with the old hardcoded False,
            # phase_9_reconcile() returns `not result.halted` = True regardless, so
            # orchestrator.py never calls halt_manager.set_halt_flag() for Phase 9 (unlike
            # Phase 1/2, which do) and Phase 8 submits real orders on the very next run despite
            # a provably broken broker/DB relationship. Only escalate to a real halt in "auto"
            # mode - non-auto (paper/dry/review) reconciliation failures (e.g. broker
            # unavailable during local dev) still just degrade, matching Phase 2's identical
            # is_credential_error-in-paper-mode distinction.
            execution_mode = config.get("execution_mode")
            is_governance_halt = execution_mode == "auto"
            if is_governance_halt:
                phase_error = f"Phase 9 reconciliation governance halt (execution_mode=auto): {error_msg}"
                logger.critical(
                    "[PHASE 9] GOVERNANCE HALT: reconciliation failure in execution_mode=auto "
                    "(real money) - broker/DB portfolio state cannot be verified. Halting until resolved."
                )

            data = {
                "reconciliation": result,
            }

        # Validate schema contract before returning
        from algo.orchestrator.phase_data_contract import validate_phase_data

        validate_phase_data(9, data)

        # CRITICAL: Final consistency check - close any positions whose trades are all closed
        # CRITICAL FIX: Must satisfy THREE conditions:
        # 1. Position is 'open' (not already closed)
        # 2. Position HAS at least one trade (position_id exists in algo_trades)
        # 3. Position's ALL trades are closed (no open/pending trades)
        # Do NOT close positions with zero trades - those are data errors to investigate
        orphans_fixed = False
        try:
            # DEBUG: Log what positions will be closed
            with DatabaseContext("read") as debug_cursor:
                debug_cursor.execute("""
                    SELECT p.position_id, p.symbol, COUNT(t.id) as trade_count,
                           STRING_AGG(t.status, ',') as statuses
                    FROM algo_positions p
                    LEFT JOIN algo_trades t ON t.position_id = p.position_id
                    WHERE p.status = 'open'
                    AND EXISTS (
                        SELECT 1 FROM algo_trades t
                        WHERE t.position_id = p.position_id LIMIT 1
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM algo_trades t
                        WHERE t.position_id = p.position_id
                        AND t.status IN ('open', 'pending', 'filled', 'partially_filled', 'paper_pending')
                    )
                    GROUP BY p.position_id, p.symbol
                """)
                orphans_to_close = debug_cursor.fetchall()
                if orphans_to_close:
                    logger.info(f"[PHASE 9 DEBUG] Found {len(orphans_to_close)} positions to close:")
                    for _, symbol, count, statuses in orphans_to_close:
                        logger.info(f"  {symbol}: {count} trades with statuses={statuses}")

            with DatabaseContext("write") as sync_cursor:
                # CRITICAL FIX 2026-08-08: Set profit_loss_dollars when closing positions
                sync_cursor.execute("""
                    UPDATE algo_positions p
                    SET status = 'closed', closed_at = CURRENT_TIMESTAMP,
                        unrealized_pnl = NULL,
                        profit_loss_dollars = COALESCE(profit_loss_dollars, 0),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE p.status = 'open'
                    AND EXISTS (
                        SELECT 1 FROM algo_trades t
                        WHERE t.position_id = p.position_id LIMIT 1
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM algo_trades t
                        WHERE t.position_id = p.position_id
                        AND t.status IN ('open', 'pending', 'filled', 'partially_filled', 'paper_pending')
                    );
                """)
                if sync_cursor.rowcount > 0:
                    logger.info(
                        f"[PHASE 9 FINAL SYNC] Closed {sync_cursor.rowcount} positions where all trades completed"
                    )
                    orphans_fixed = True
        except Exception as sync_err:
            logger.warning(f"[PHASE 9 FINAL SYNC] Could not close positions: {sync_err}")

        # If we fixed orphaned positions, mark it in the log so next run clears halt flag
        if orphans_fixed:
            logger.warning(
                "[PHASE 9] Fixed orphaned positions - halt flag will auto-clear on next Phase 1 data freshness check"
            )

        # CRITICAL: Log final consolidated phase result (not a sub-step)
        # Phase 9 logs multiple sub-steps (reconciliation, portfolio_snapshot, weight_optimization, etc.)
        # but the orchestrator's phase_results[9] must contain the OVERALL phase status, not the last sub-step.
        # This ensures the halt_reason accurately reports Phase 9's overall outcome, not a specific sub-step.
        # Without this, when Phase 1 fails, the halt_reason incorrectly shows the last Phase 9 sub-step message
        # instead of the Phase 1 error - a governance violation (inaccurate error reporting).
        phase_summary = f"Portfolio state: {data.get('portfolio_value', 'N/A')} | Status: {phase_status}"
        log_phase_result_fn(9, "reconciliation", phase_status, phase_summary)

        return PhaseResult(9, "reconciliation", phase_status, data, is_governance_halt, phase_error)

    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        full_traceback = traceback.format_exc()
        logger.critical(
            f"[PHASE 9 CRITICAL] Unexpected error ({error_type}): {error_msg}. "
            "Full traceback above. Cannot proceed with trading when portfolio state is unknown. "
            "Setting halt flag to prevent further trading until broker is accessible.",
            exc_info=True,
        )
        # CRITICAL: Include full traceback in summary so it persists to execution log.
        # Was truncating error_msg to 100 chars, which cut real Postgres errors (e.g.
        # "column X of relation Y does not exist") off mid-word before the useful part -
        # exactly the "halted, not sure why" blind spot this logging exists to prevent.
        error_summary = f"{error_type}: {error_msg[:500]}\n{full_traceback[:1500]}"
        log_phase_result_fn(9, "reconciliation", "error", error_summary)
        return PhaseResult(
            9,
            "reconciliation",
            "error",
            {"status": "error", "reason": f"Phase 9 error ({error_type}): {error_msg[:500]}", "positions": 0},
            True,
            f"Phase 9 error ({error_type}): {error_msg[:500]}",
        )
