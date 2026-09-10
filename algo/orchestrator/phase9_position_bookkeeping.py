#!/usr/bin/env python3
"""Stale-exit-price audit and trade_ids_arr bookkeeping - split out of
phase9_reconciliation.py (2026-09-10, file-size ratchet: that file crossed the 2000-line
hard ceiling) to keep it under the cap. Methods are verbatim, no behavior change.
"""

import logging
from collections.abc import Callable
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext
from utils.trading import TradeStatus

logger = logging.getLogger(__name__)


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
