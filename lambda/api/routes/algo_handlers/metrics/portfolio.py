"""Algo metrics handler: /api/algo/portfolio.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds `_get_algo_portfolio` and its private `_ensure_portfolio_fields`
helper (used only by this handler, so it stays here rather than in `_shared.py`);
the other handlers live in their own sibling modules (or, for
`_get_portfolio_summary`, directly in `__init__.py` - see that file's docstring for
why). All names are re-exported from `algo_handlers/metrics/__init__.py` so
existing callers (e.g. routes/algo.py's
`from .algo_handlers.metrics import (...)`) require zero changes. Pure move, no
logic changed - body is byte-for-byte identical to the pre-split version (only the
import header differs, trimmed to this function's actual dependencies).
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
import logging
from typing import Any

import psycopg2
from psycopg2.extensions import cursor
from routes.utils import (
    db_route_handler,
    error_response,
    safe_dict_convert,
    success_response,
    validate_api_response,
)

from utils.validation import format_decimal_string

logger = logging.getLogger(__name__)


def _ensure_portfolio_fields(data: dict[str, Any]) -> Any:
    """Validate portfolio response has all required fields. Fail-fast if missing.

    CRITICAL: Portfolio value and cash must never be None - they're essential for trading.
    If data is missing, return error instead of adding defaults.
    """
    if not isinstance(data, dict):
        return data

    if data.get("_error"):
        return data

    # FAIL-FAST: Critical fields must exist and be non-None
    required_fields = ["total_portfolio_value", "total_cash", "position_count"]
    for field in required_fields:
        if field not in data:
            return {"_error": f"Portfolio critical field missing: {field}"}
        if data[field] is None:
            return {"_error": f"Portfolio critical field is None: {field}"}

    return data


@db_route_handler("get algo portfolio")
@validate_api_response("port")
def _get_algo_portfolio(cur: cursor) -> Any:
    """Get latest portfolio snapshot data with structured unrealized PnL breakdown.

    FAIL-FAST: Returns error if portfolio snapshots are unavailable.
    No placeholder/fallback data - portfolio value is critical for trading.
    """
    try:
        # NOTE: aliases adjusted_drawdown_pct (cash-flow-adjusted, migration 1134) as
        # max_drawdown_pct in the response so this endpoint agrees with the circuit
        # breaker and risk dashboard instead of showing the raw, capital-flow-conflated
        # figure - see steering/GOVERNANCE.md and algo/risk/circuit_breaker.py::_check_drawdown.
        cur.execute("""
            SELECT snapshot_date, total_portfolio_value, total_cash,
                   unrealized_pnl_total, position_count, daily_return_pct, unrealized_pnl_pct,
                   cumulative_return_pct, adjusted_drawdown_pct AS max_drawdown_pct, largest_position_pct,
                   unrealized_pnl_winning_count, unrealized_pnl_losing_count, unrealized_pnl_breakeven_count,
                   unrealized_pnl_source, created_at, updated_at
            FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        # Return sensible defaults if no portfolio snapshots available yet
        if row is None:
            logger.info("Portfolio snapshot unavailable - returning bootstrap defaults")
            response_data = {
                "total_portfolio_value": "0.00",
                "total_cash": "0.00",
                "position_count": 0,
                "daily_return_pct": "0.00",
                "unrealized_pnl": {
                    "total_dollars": "0.00",
                    "total_pct": "0.00",
                    "winning_positions": 0,
                    "losing_positions": 0,
                    "breakeven_positions": 0,
                    "source": "bootstrap",
                    "note": "Portfolio not yet initialized",
                },
                "cumulative_return_pct": "0.00",
                "max_drawdown_pct": None,
                "largest_position_pct": None,
                "last_run": None,
                "data_age_seconds": 0,
            }
            validated_data = _ensure_portfolio_fields(response_data)
            return success_response(validated_data)
        data = safe_dict_convert(row)
        pv = format_decimal_string(data.get("total_portfolio_value"), precision=2, allow_none=True)
        position_count_val = data.get("position_count")
        if position_count_val is None:
            logger.error("Portfolio snapshot incomplete: position_count missing")
            return error_response(
                503,
                "incomplete_snapshot",
                "Portfolio snapshot missing position_count field. "
                "Cannot assess portfolio composition. Check algo_portfolio_snapshots table schema.",
            )
        position_count = int(position_count_val)
        winning_count_val = data.get("unrealized_pnl_winning_count")
        winning_count = int(winning_count_val) if winning_count_val is not None else 0
        losing_count_val = data.get("unrealized_pnl_losing_count")
        losing_count = int(losing_count_val) if losing_count_val is not None else 0
        breakeven_count_val = data.get("unrealized_pnl_breakeven_count")
        breakeven_count = int(breakeven_count_val) if breakeven_count_val is not None else 0

        # Calculate data_age_seconds from updated_at timestamp (REQUIRED, no fallback)
        # CRITICAL: snapshot_date is a DATE column (midnight); created_at only reflects the
        # FIRST insert for that date and never changes on subsequent ON CONFLICT DO UPDATEs
        # within the same trading day, so using it made every same-day re-run after the first
        # appear increasingly stale even though the row's values were current. updated_at is
        # explicitly bumped (`updated_at = NOW()`) on every upsert in
        # algo/infrastructure/reconciliation.py and algo/orchestrator/phase9_reconciliation.py,
        # so it actually reflects the last write. Confirmed live 2026-07-07: portfolio panel
        # reported 53796s stale immediately after a fresh Phase 9 write.
        # Get database time as naive timestamp in the database's configured timezone to match snapshot timestamps
        # CRITICAL FIX: Snapshots are stored as TIMESTAMP WITHOUT TIME ZONE in the database's local timezone (America/Chicago = CT).
        # The database returns NOW() with timezone info, so we must explicitly cast to timestamp without timezone
        # to match the snapshot column type. This avoids "can't subtract offset-naive and offset-aware datetimes" error.
        try:
            # Cast to TIMESTAMP (without timezone) to match snapshot column type (TIMESTAMP WITHOUT TIME ZONE)
            cur.execute("SELECT NOW()::timestamp")
            now_row = cur.fetchone()
            if not now_row:
                raise ValueError("Database NOW() returned empty")
            now_row = safe_dict_convert(now_row)
            now_db = now_row.get("now")
            if now_db is None:
                # FAIL-FAST: Database NOW() must return a value
                raise ValueError("Database NOW()::timestamp returned NULL")
        except Exception as e:
            logger.error(f"CRITICAL: Cannot get database NOW(): {e}")
            return error_response(503, "database_error", "Cannot get current database time")

        from datetime import datetime

        # FAIL-FAST: Portfolio snapshots must have updated_at timestamp (required column)
        # Do NOT fall back to created_at - if updated_at is missing, that's a data integrity issue
        last_write_at = data.get("updated_at")
        if last_write_at is None:
            logger.error("CRITICAL: updated_at missing from portfolio snapshot. Data integrity check failed.")
            return error_response(503, "incomplete_data", "Portfolio snapshot missing required updated_at timestamp")

        # Calculate age: both are now naive TIMESTAMP WITHOUT TIME ZONE in database's local timezone
        if isinstance(last_write_at, datetime) and isinstance(now_db, datetime):
            # Both should be naive datetimes in the database's local timezone
            # Verify they're both naive before subtracting
            if last_write_at.tzinfo is not None or now_db.tzinfo is not None:
                # If either has timezone info, strip it for comparison
                if last_write_at.tzinfo is not None:
                    last_write_at = last_write_at.replace(tzinfo=None)
                if now_db.tzinfo is not None:
                    now_db = now_db.replace(tzinfo=None)
                logger.warning(
                    f"[PORTFOLIO] Stripped timezone info from timestamps: last_write={last_write_at}, now={now_db}"
                )
            data_age_seconds = int((now_db - last_write_at).total_seconds())
        else:
            logger.error(
                f"CRITICAL: Time mismatch - now_db={type(now_db).__name__}, last_write_at={type(last_write_at).__name__}"
            )
            return error_response(503, "data_corruption", "Cannot calculate portfolio age - type mismatch")

        response_data = {
            "total_portfolio_value": pv,
            "total_cash": format_decimal_string(data.get("total_cash"), precision=2, allow_none=True),
            "position_count": position_count,
            "daily_return_pct": format_decimal_string(data.get("daily_return_pct"), precision=2, allow_none=True),
            "unrealized_pnl": {
                "total_dollars": format_decimal_string(data.get("unrealized_pnl_total"), precision=2, allow_none=True),
                "total_pct": format_decimal_string(data.get("unrealized_pnl_pct"), precision=2, allow_none=True),
                "winning_positions": winning_count,
                "losing_positions": losing_count,
                "breakeven_positions": breakeven_count,
                "source": data.get("unrealized_pnl_source", "open_positions_only"),
                "note": "Includes only open positions (no closed trades, no dividends)",
            },
            "cumulative_return_pct": format_decimal_string(
                data.get("cumulative_return_pct"), precision=2, allow_none=True
            ),
            "max_drawdown_pct": format_decimal_string(data.get("max_drawdown_pct"), precision=2, allow_none=True),
            "largest_position_pct": format_decimal_string(
                data.get("largest_position_pct"), precision=2, allow_none=True
            ),
            "last_run": data.get("snapshot_date"),
            "data_age_seconds": data_age_seconds,
        }
        validated_data = _ensure_portfolio_fields(response_data)

        return success_response(validated_data)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"CRITICAL: Portfolio fetch database error: {type(e).__name__}: {e}")
        return error_response(503, "data_unavailable", f"Portfolio data unavailable: {type(e).__name__}")
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"CRITICAL: Portfolio data format error: {type(e).__name__}: {e}")
        return error_response(
            500,
            "data_format_error",
            f"Portfolio data format invalid: {type(e).__name__}",
        )
    except (AttributeError, KeyError) as e:
        logger.error(
            f"CRITICAL: Portfolio fetch unexpected error: {type(e).__name__}: {e}",
            exc_info=True,
        )
        return error_response(503, "service_error", f"Portfolio service error: {type(e).__name__}")
