"""Review persistence/logging and open-position-listing methods for PositionMonitor,
extracted from algo/monitoring/position_monitor.py (2026-09-05, file-size ratchet: that file
is a Tier-2 bloater flagged for decomposition, same pattern already used for
`algo/monitoring/position_corporate_actions.py`'s CorporateActionsMixin). Bodies are
verbatim, no logic changed - mixed into PositionMonitor, which still defines the `config`
instance attribute these methods read via `self`.

`DatabaseContext` is accessed via the position_monitor module object at call time (not
imported by name here) because existing tests patch
`algo.monitoring.position_monitor.DatabaseContext` expecting that to affect these methods -
a plain import here would silently stop seeing those patches (same reasoning as
position_corporate_actions.py / position_order_management.py). `algo.monitoring.
position_monitor` itself imports this module at load time, so the reference is resolved
lazily (inside the method bodies, not at import time) to avoid a circular-import failure.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

import algo.monitoring.position_monitor as _pm

logger = logging.getLogger(__name__)


class PositionReportingMixin:
    """Position-review persistence, console reporting, and open-position-listing methods
    for PositionMonitor. Not usable standalone - relies on the `config` instance attribute
    defined on PositionMonitor itself.
    """

    config: Any

    def _persist_review(self, rec: dict[str, Any], cur: PsycopgCursor[Any], position_index: int) -> None:
        """Update algo_positions with current price/PnL and log a monitoring audit row (atomic).

        Uses savepoint to ensure both position update and audit log succeed together.
        If audit log fails, both are rolled back.
        """
        sp_name = f"sp_persist_review_{position_index}"
        cur.execute(f"SAVEPOINT {sp_name}")
        try:
            if "current_price" not in rec or rec["current_price"] is None:
                raise ValueError(
                    f"Cannot persist review for position {rec['position_id']}: current_price missing or None"
                )
            if "quantity" not in rec or rec["quantity"] is None:
                raise ValueError(f"Cannot persist review for position {rec['position_id']}: quantity missing or None")

            try:
                current_price = float(rec["current_price"])
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"Invalid current_price {rec['current_price']} for position {rec['position_id']}: {e}"
                ) from e

            try:
                quantity = float(rec["quantity"])
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid quantity {rec['quantity']} for position {rec['position_id']}: {e}") from e

            cur.execute(
                """
                UPDATE algo_positions
                SET current_price = %s,
                    position_value = %s * %s,
                    unrealized_pnl = (%s - avg_entry_price) * %s,
                    unrealized_pnl_pct = CASE WHEN avg_entry_price > 0 THEN ((%s - avg_entry_price) / avg_entry_price) * 100 ELSE NULL END,
                    -- r_multiple was written once at entry as a hardcoded 1.0 "baseline" (see
                    -- executor_entry_handler.py._record_entry_phase) and never touched again, so
                    -- the positions dashboard's "R" column silently showed +1.00R for every open
                    -- position regardless of actual price movement. Recompute it live every cycle
                    -- against the original stop_loss_price (not current_stop_price, which trailing
                    -- stops may have raised) - same convention executor_exit_handler.py uses for
                    -- exit_r_multiple, so an open position's R stays comparable to its eventual
                    -- closed R rather than resetting when the stop is trailed.
                    r_multiple = CASE WHEN (avg_entry_price - stop_loss_price) > 0
                                      THEN (%s - avg_entry_price) / (avg_entry_price - stop_loss_price)
                                      ELSE NULL END,
                    days_since_entry = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    current_price,
                    quantity,
                    current_price,
                    current_price,
                    quantity,
                    current_price,
                    current_price,
                    int(rec["days_held"]),
                    rec["position_id"],
                ),
            )
            # Log the review to audit (atomic with position update)
            cur.execute(
                """
                INSERT INTO algo_audit_log (action_type, symbol, action_date,
                                            details, actor, status, created_at)
                VALUES ('position_review', %s, CURRENT_TIMESTAMP, %s, 'position_monitor',
                        %s, CURRENT_TIMESTAMP)
                """,
                (
                    rec["symbol"],
                    json.dumps(
                        {
                            "trade_id": rec["trade_id"],
                            "r_multiple": rec["r_multiple"],
                            "unrealized_pct": rec["unrealized_pct"],
                            "flags": rec["flags"],
                            "rs_label": rec["rs_label"],
                            "sector_state": rec["sector_state"],
                            "action": rec["action"],
                            "action_reason": rec["action_reason"],
                            "days_to_earnings": rec["days_to_earnings"],
                            "proposed_stop": float(rec["proposed_stop"]),
                        }
                    ),
                    rec["action"],
                ),
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute(f"ROLLBACK TO {sp_name}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError, psycopg2.ProgrammingError) as rb_err:
                logger.warning(f"[POSITION_MONITOR] Could not rollback savepoint {sp_name}: {rb_err}")
            # CRITICAL FIX: Escape exception message to prevent f-string format error
            safe_error = str(e).replace("{", "{{").replace("}", "}}")
            logger.error(f"Failed to persist review for {rec['symbol']}: {safe_error}")
            raise

    def _print_recommendation(self, rec: dict[str, Any]) -> None:
        flags_str = ", ".join(rec["flags"]) if rec["flags"] else "none"
        logger.info(
            f"  {rec['symbol']:6s}  qty={int(rec['quantity']):<5d} "
            f"price=${rec['current_price']:7.2f}  "
            f"R={rec['r_multiple']:+.2f}  "
            f"P&L={rec['unrealized_pct']:+.2f}%  "
            f"days={rec['days_held']:<3d} "
            f"hits={rec['target_hits']}  "
            f"flags={flags_str}"
        )

    def get_open_positions(self) -> list[dict[str, str]]:
        """Get list of open positions for halt checking and monitoring.

        Returns a list of dicts with at least 'symbol' and optionally 'name'.
        Used by orchestrator for single-stock halt detection.

        Raises:
            RuntimeError: If position data cannot be retrieved from database (fail-fast for visibility)
        """
        with _pm.DatabaseContext("read") as cur:  # type: ignore[attr-defined]
            try:
                cur.execute("""
                    SELECT DISTINCT symbol FROM algo_positions
                    WHERE status = 'open' AND quantity > 0
                    ORDER BY symbol
                """)
                positions = cur.fetchall()
                return [{"symbol": row[0], "name": row[0]} for row in positions] if positions else []
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"Failed to fetch open positions from database: {e}. "
                    f"Cannot proceed with halt checking and position monitoring without access to position data."
                ) from e
