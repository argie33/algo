#!/usr/bin/env python3
"""Track and manage position state in database."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import psycopg2

from utils.db import DatabaseContext, OptimisticLockRetry
from utils.trading import PositionStatus

logger = logging.getLogger(__name__)


class PositionTracker:
    """Manage all position-related database operations and validation."""

    def __init__(self, alpaca_key: str, alpaca_secret: str, alpaca_base_url: str):
        self.alpaca_key = alpaca_key
        self.alpaca_secret = alpaca_secret
        self.alpaca_base_url = alpaca_base_url

    def setup_position_data(
        self,
        trade_id: str,
        symbol: str,
        actual_shares: Decimal,
        executed_price: Decimal,
        stop_loss_price: Decimal,
    ) -> dict[str, Any]:
        """Build comprehensive position insertion data.

        Returns dict with position_id, symbol, quantity, avg_entry_price, current_price,
        position_value, and initial stop levels.
        """
        position_id = f"POS-{trade_id}"
        position_value = Decimal(str(actual_shares)) * Decimal(str(executed_price))

        if position_value <= 0:
            raise ValueError(
                f"Invalid position value: {actual_shares} shares @ ${executed_price:.2f} = ${position_value:.2f}"
            )

        return {
            "position_id": position_id,
            "symbol": symbol,
            "quantity": actual_shares,
            "avg_entry_price": executed_price,
            "current_price": executed_price,
            "position_value": position_value,
            "stop_loss_price": stop_loss_price,
            "current_stop_price": stop_loss_price,
        }

    def update_position_with_retry(
        self,
        cur: Any,
        position_id: int,
        new_qty: float,
        new_stop_price: Decimal | float | None = None,
        full_exit: bool = False,
        exit_stage: str | None = None,
    ) -> tuple[bool, str | None]:
        """Update position with retry logic for race condition safety.

        Handles concurrent updates by re-reading position before each retry.
        Returns: (success: bool, message: str or None)
        """

        def do_update() -> bool:
            cur.execute(
                "SELECT quantity, current_stop_price FROM algo_positions WHERE position_id = %s",
                (position_id,),
            )
            result = cur.fetchone()
            if not result:
                raise ValueError(f"Position {position_id} not found")

            current_qty = result[0]
            # CRITICAL: Keep stop price as Decimal to avoid floating-point rounding errors
            # in financial calculations. Convert to float only for display/logging.
            current_stop = Decimal(str(result[1])) if result[1] is not None else None
            if current_stop is None:
                raise ValueError(f"Position {position_id} missing current_stop_price")

            effective_stop = new_stop_price
            if new_stop_price is not None:
                # Convert new_stop_price to Decimal for proper comparison
                new_stop_decimal = Decimal(str(new_stop_price))
                if current_stop >= new_stop_decimal:
                    effective_stop = current_stop

            if full_exit or new_qty <= 0:
                cur.execute(
                    """UPDATE algo_positions
                       SET status = %s, quantity = 0, closed_at = CURRENT_TIMESTAMP
                       WHERE position_id = %s AND quantity = %s""",
                    (PositionStatus.CLOSED.value, position_id, current_qty),
                )
            else:
                # Validate target_levels_hit is populated (critical for exit sequencing)
                cur.execute(
                    "SELECT target_levels_hit FROM algo_positions WHERE position_id = %s",
                    (position_id,),
                )
                th_row = cur.fetchone()
                if th_row is None:
                    raise ValueError(f"Position {position_id} not found during partial exit update")
                target_levels_hit = th_row[0]
                if target_levels_hit is None:
                    raise ValueError(
                        f"Position {position_id} has NULL target_levels_hit. "
                        "Cannot safely record target exit without exit history."
                    )

                increment_targets = 1 if (exit_stage and "target" in exit_stage.lower()) else 0
                new_target_levels = target_levels_hit + increment_targets
                update_sql = """UPDATE algo_positions
                               SET quantity = %s,
                                   position_value = %s * current_price,
                                   target_levels_hit = %s,
                                   current_stop_price = %s"""
                params = [new_qty, new_qty, new_target_levels, effective_stop]

                if exit_stage == "target_1":
                    update_sql += ", target_1_hit_time = CURRENT_TIMESTAMP"
                elif exit_stage == "target_2":
                    update_sql += ", target_2_hit_time = CURRENT_TIMESTAMP"
                elif exit_stage == "target_3":
                    update_sql += ", target_3_hit_time = CURRENT_TIMESTAMP"

                update_sql += " WHERE position_id = %s AND quantity = %s"
                params.extend([position_id, current_qty])

                logger.debug(
                    f"[POSITION_UPDATE] partial exit: position={position_id}, "
                    f"old_qty={current_qty}, new_qty={new_qty}, exit_stage={exit_stage}"
                )
                cur.execute(update_sql, params)
                rows_updated = cur.rowcount
                logger.debug(
                    f"[POSITION_UPDATE] update result: position={position_id}, rows_affected={rows_updated}"
                )

            return bool(cur.rowcount > 0)

        success = OptimisticLockRetry.retry_on_race_condition(
            do_update,
            operation_name=f"update_position_{position_id}",
            max_attempts=3,
            base_delay_ms=100,
            query="UPDATE algo_positions SET ... WHERE position_id=%s AND quantity=%s",
            params=(new_qty, position_id, new_qty),
            context={"position_id": position_id, "new_quantity": new_qty},
        )

        if not success:
            # Log the race condition with more context
            logger.error(
                f"[POSITION_UPDATE] Race condition after 3 retries: position={position_id}, "
                f"expected_new_qty={new_qty}. Possible causes: (1) another process is modifying the position "
                f"(check Phase 3 position monitor concurrent timing), (2) failed optimistic lock, "
                f"(3) data consistency issue in algo_positions table"
            )

        if success:
            return True, None
        else:
            return (
                False,
                "Position quantity changed before update (race condition, retries exhausted)",
            )

    def _with_cursor(self, operation: Any, acquire_locks: bool = False) -> Any:
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("write") as cur:
                if acquire_locks:
                    from utils.db.advisory_locks import (
                        ALGO_POSITIONS_LOCK_ID,
                        ALGO_TRADES_LOCK_ID,
                        acquire_advisory_lock,
                        release_advisory_lock,
                    )

                    acquire_advisory_lock(cur, ALGO_TRADES_LOCK_ID, "algo_trades")
                    acquire_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                    try:
                        return operation(cur)
                    finally:
                        release_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                        release_advisory_lock(cur, ALGO_TRADES_LOCK_ID, "algo_trades")
                else:
                    return operation(cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Database operation failed: {e}")
            raise
