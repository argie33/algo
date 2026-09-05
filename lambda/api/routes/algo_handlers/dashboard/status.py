"""Algo dashboard handler: /api/algo/status.

Split 2026-09-05 out of the original 2160-line algo_handlers/dashboard.py (see
positions.py's module docstring for the full split rationale). This module holds only
`_get_algo_status`. Pure move, no logic changed.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    safe_dict_convert,
    validate_api_response,
)

from utils.validation import format_decimal_string

logger = logging.getLogger(__name__)


@db_route_handler("fetch algo status")
@validate_api_response("run")
def _get_algo_status(cur: cursor) -> Any:  # noqa: C901
    """Get latest algo execution status plus latest portfolio snapshot.

    Returns sensible defaults if data is missing, allowing dashboard to render
    instead of showing "Panel Unavailable" error.
    """
    cur.execute("""
            SELECT
                details->>'run_id' AS run_id,
                action_type,
                action_date,
                details->>'summary' AS message,
                status,
                created_at
            FROM algo_audit_log
            ORDER BY created_at DESC
            LIMIT 1
        """)
    row = cur.fetchone()

    # If no audit log, use sensible defaults
    if row is None:
        row = {
            "run_id": "not_started",
            "action_type": "INIT",
            "action_date": None,
            "message": "No trading activity yet",
            "status": "ready",
        }
    else:
        row = safe_dict_convert(row)

    # Fetch and validate portfolio snapshot: RESILIENT fallback to computed data
    # If orchestrator hasn't run (Phase 9 snapshot missing), compute from algo_positions + algo_trades
    portfolio = None
    try:
        cur.execute("""
                SELECT total_portfolio_value, total_cash, daily_return_pct,
                       unrealized_pnl_total, position_count
                FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """)
        snap = cur.fetchone()
        if snap is not None:
            snap = safe_dict_convert(snap)
            pv_raw = snap.get("total_portfolio_value")
            tc_raw = snap.get("total_cash")
            pc_raw = snap.get("position_count")
            unrealized_pnl_raw = snap.get("unrealized_pnl_total")
            daily_return_raw = snap.get("daily_return_pct")

            if pv_raw is None or tc_raw is None or pc_raw is None:
                logger.warning("[PORTFOLIO] Snapshot has NULL critical fields, falling back to computed portfolio")
            else:
                try:
                    pv = float(pv_raw)
                    tc_float = float(tc_raw)
                    pc = int(pc_raw)
                    unrealized_pnl = float(unrealized_pnl_raw) if unrealized_pnl_raw is not None else None
                    unrealized_pnl_pct = None
                    if pv > 0 and unrealized_pnl is not None:
                        unrealized_pnl_pct = unrealized_pnl / pv * 100
                    elif unrealized_pnl is None:
                        logger.warning("[PORTFOLIO] unrealized_pnl_total is NULL in snapshot - data unavailable")

                    portfolio = {
                        "total_portfolio_value": format_decimal_string(pv, precision=2, allow_none=True),
                        "total_cash": format_decimal_string(tc_float, precision=2),
                        "position_count": pc,
                        "daily_return_pct": format_decimal_string(
                            float(daily_return_raw) if daily_return_raw is not None else None,
                            precision=2,
                            allow_none=True,
                        ),
                        "unrealized_pnl_pct": format_decimal_string(
                            unrealized_pnl_pct,
                            precision=2,
                            allow_none=True,
                        ),
                        "unrealized_pnl_dollars": round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
                    }
                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"[PORTFOLIO] Snapshot data type conversion failed, falling back to computed: {type(e).__name__}: {e}"
                    )

        if portfolio is None:
            # FALLBACK: Compute portfolio from algo_positions + algo_trades when snapshot unavailable
            # This allows dashboard to show data even if orchestrator hasn't run Phase 9
            logger.info(
                "[PORTFOLIO] algo_portfolio_snapshots empty or unavailable, computing from algo_positions + algo_trades"
            )
            cur.execute("""
                SELECT
                  COUNT(DISTINCT symbol) as pos_count,
                  SUM(position_value) as total_positions_value,
                  SUM(CASE WHEN status='closed' THEN quantity * current_price ELSE 0 END) as closed_value
                FROM algo_positions
                WHERE status IN ('open', 'closed')
            """)
            pos_result = cur.fetchone()
            if pos_result:
                pos_result = safe_dict_convert(pos_result)

            # FAIL-FAST: Query must return result. If table empty, this is a data quality issue.
            if not pos_result:
                raise RuntimeError(
                    "[PORTFOLIO FALLBACK] algo_positions query returned no result. "
                    "Cannot compute fallback portfolio without position data. "
                    "Check: (1) algo_positions table populated? (2) Schema intact?"
                )

            # Extract position metrics - NO fallback to 0 for these critical fields
            pos_count_raw = pos_result.get("pos_count")
            if pos_count_raw is None:
                raise ValueError("[PORTFOLIO FALLBACK] pos_count is NULL - cannot compute position count")
            try:
                pos_count = int(pos_count_raw)
            except (ValueError, TypeError) as e:
                raise ValueError(f"[PORTFOLIO FALLBACK] pos_count invalid ({pos_count_raw}): {e}") from e

            pos_value_raw = pos_result.get("total_positions_value")
            if pos_value_raw is None:
                raise ValueError("[PORTFOLIO FALLBACK] total_positions_value is NULL - cannot compute position value")
            try:
                pos_value = float(pos_value_raw)
            except (ValueError, TypeError) as e:
                raise ValueError(f"[PORTFOLIO FALLBACK] total_positions_value invalid ({pos_value_raw}): {e}") from e

            closed_value_raw = pos_result.get("closed_value")
            if closed_value_raw is None:
                raise ValueError("[PORTFOLIO FALLBACK] closed_value is NULL - cannot compute closed position value")
            try:
                closed_value = float(closed_value_raw)
            except (ValueError, TypeError) as e:
                raise ValueError(f"[PORTFOLIO FALLBACK] closed_value invalid ({closed_value_raw}): {e}") from e

            # Get initial cash from portfolio snapshot if available
            # CRITICAL: algo_trades table does NOT have initial_cash column
            initial_cash = None

            # Try to get actual initial balance from first portfolio snapshot
            cur.execute("""
                SELECT total_portfolio_value
                FROM algo_portfolio_snapshots
                ORDER BY created_at ASC LIMIT 1
            """)
            first_snapshot = cur.fetchone()
            if first_snapshot:
                first_snapshot = safe_dict_convert(first_snapshot)

            if first_snapshot is not None and "total_portfolio_value" in first_snapshot:
                initial_cash_raw = first_snapshot.get("total_portfolio_value")
                # FAIL-FAST: Explicit None check (not falsy check - 0.0 is valid)
                if initial_cash_raw is None:
                    raise RuntimeError(
                        "[PORTFOLIO] First portfolio snapshot has NULL total_portfolio_value. "
                        "Cannot determine initial portfolio value. Check data integrity."
                    )
                try:
                    initial_cash = float(initial_cash_raw)
                except (ValueError, TypeError) as e:
                    raise ValueError(
                        f"[PORTFOLIO] First snapshot total_portfolio_value invalid ({initial_cash_raw}): {e}"
                    ) from e

            # If no snapshot available, fail rather than using hardcoded fallback
            if initial_cash is None:
                raise RuntimeError(
                    "[PORTFOLIO FALLBACK] No portfolio snapshots available to determine initial balance. "
                    "Cannot compute fallback portfolio. Orchestrator may not have completed initialization. "
                    "Check: (1) algo_portfolio_snapshots table has records? (2) Orchestrator Phase 9 completed?"
                )

            # Compute cash as: initial - (all positions value) + (closed positions)
            total_spent = pos_value
            tc_float = initial_cash - total_spent + closed_value
            pv = tc_float + pos_value

            portfolio = {
                "total_portfolio_value": format_decimal_string(pv, precision=2, allow_none=True),
                "total_cash": format_decimal_string(tc_float, precision=2),
                "position_count": int(pos_count),
                "daily_return_pct": None,  # Unavailable without snapshot
                "unrealized_pnl_pct": None,  # Unavailable without snapshot
                "unrealized_pnl_dollars": None,  # Unavailable without snapshot
            }
            logger.info(f"[PORTFOLIO] Computed: total_value={pv:.2f}, cash={tc_float:.2f}, positions={pos_count}")

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        import traceback

        logger.error(f"[_GET_ALGO_STATUS] Exception: {type(e).__name__}: {e}\nTraceback: {traceback.format_exc()}")
        code, error_type, message = handle_db_error(e, "fetch portfolio data")
        return error_response(code, error_type, message)

    # CRITICAL FIX: Check freshness for BOTH algo_audit_log AND algo_portfolio_snapshots
    # Root cause of "portfolio stale" errors: only audit_log was checked, allowing 24h-old portfolio data
    audit_freshness = check_data_freshness(cur, "algo_audit_log", "created_at", warning_days=1)
    portfolio_freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)

    # Use portfolio freshness as the primary freshness indicator (data_freshness returned to frontend)
    # Include both checks in response so frontend can detect stale portfolio data
    combined_freshness = portfolio_freshness.copy() if portfolio_freshness else {}
    combined_freshness["audit_log_freshness"] = audit_freshness

    # Map audit status to success boolean for API contract
    # Status can be: "success", "halted", "error", or other phase-specific statuses
    success = row["status"] == "success" if row["status"] else False

    return json_response(
        200,
        {
            "run_id": row["run_id"],
            "success": success,
            "last_run": row["action_date"].isoformat() if row["action_date"] else None,
            "current_phase": row["action_type"],
            "status": row["status"],
            "message": row["message"],
            "portfolio": portfolio,
            "data_freshness": combined_freshness,
        },
    )
