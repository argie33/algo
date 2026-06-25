#!/usr/bin/env python3
"""Track and manage position state in database."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import psycopg2
import requests

from algo.infrastructure import get_api_timeout
from algo.trading.exceptions import DataUnavailableError
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
        new_stop_price: float | None = None,
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
            current_stop = float(result[1])

            effective_stop = new_stop_price
            if new_stop_price and current_stop >= new_stop_price:
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

                cur.execute(update_sql, params)

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

        if success:
            return True, None
        else:
            return (
                False,
                "Position quantity changed before update (race condition, retries exhausted)",
            )

    def validate_position_against_alpaca(self, symbol: str) -> dict[str, Any]:
        """Validate that local DB position matches Alpaca position for a symbol.

        Called immediately after order placement to detect partial fills early.
        If Alpaca has a different quantity than our DB, corrects the DB to match.

        Returns: {
            'valid': bool,
            'db_quantity': int,
            'alpaca_quantity': int,
            'corrected': bool,
            'message': str
        }
        """
        try:
            resp = requests.get(
                f"{self.alpaca_base_url}/v2/positions/{symbol}",
                headers={
                    "APCA-API-KEY-ID": self.alpaca_key,
                    "APCA-API-SECRET-KEY": self.alpaca_secret,
                },
                timeout=get_api_timeout(),
            )

            if resp.status_code == 404:
                # Position doesn't exist in Alpaca yet (order not filled)
                return {
                    "valid": True,
                    "db_quantity": None,
                    "alpaca_quantity": 0,
                    "corrected": False,
                    "message": f"{symbol}: position not yet filled in Alpaca",
                }

            if resp.status_code != 200:
                return {
                    "valid": False,
                    "db_quantity": None,
                    "alpaca_quantity": None,
                    "corrected": False,
                    "message": f"Alpaca /v2/positions/{symbol} returned HTTP {resp.status_code}",
                }

            alpaca_pos = resp.json()
            qty_raw = alpaca_pos["qty"] if "qty" in alpaca_pos else None
            if qty_raw is None:
                raise DataUnavailableError(f"Alpaca position missing 'qty' field: {alpaca_pos.keys()}")
            alpaca_qty = int(float(qty_raw))

            if alpaca_qty <= 0:
                return {
                    "valid": True,
                    "db_quantity": None,
                    "alpaca_quantity": 0,
                    "corrected": False,
                    "message": f"{symbol}: no position in Alpaca",
                }

            # Check DB for this position
            def _check_db_quantity(cur: Any) -> int | None:
                cur.execute(
                    """
                    SELECT entry_quantity FROM algo_trades
                    WHERE symbol = %s AND status IN ('open', 'filled', 'partially_filled', 'active')
                    ORDER BY trade_date DESC LIMIT 1
                """,
                    (symbol,),
                )
                row = cur.fetchone()
                return int(row[0]) if row and row[0] else None

            db_qty = self._with_cursor(_check_db_quantity)

            if db_qty is None:
                # No DB record yet - this is fine (async order, not yet in DB)
                return {
                    "valid": True,
                    "db_quantity": None,
                    "alpaca_quantity": alpaca_qty,
                    "corrected": False,
                    "message": f"{symbol}: position not yet in DB",
                }

            # Compare quantities
            if db_qty == alpaca_qty:
                return {
                    "valid": True,
                    "db_quantity": db_qty,
                    "alpaca_quantity": alpaca_qty,
                    "corrected": False,
                    "message": f"{symbol}: quantities match ({alpaca_qty}sh)",
                }

            # Mismatch detected - correct DB to match Alpaca (source of truth)
            def _correct_quantity(cur: Any) -> bool:
                cur.execute(
                    """
                    UPDATE algo_trades
                    SET entry_quantity = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE symbol = %s AND status IN ('open', 'filled', 'partially_filled', 'active')
                    ORDER BY trade_date DESC LIMIT 1
                """,
                    (alpaca_qty, symbol),
                )
                # CRITICAL: Add audit trail for partial fill correction
                # This ensures P&L calculations can be traced back to the correction event
                cur.execute(
                    """
                    INSERT INTO algo_audit_log (
                        operation_type, entity_type, entity_id, actor,
                        operation_details, created_at
                    ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        "PARTIAL_FILL_CORRECTION",
                        "trade",
                        symbol,
                        "system:position_validation",
                        f"Partial fill detected and corrected: requested {db_qty} shares, Alpaca filled {alpaca_qty} shares. "
                        f"DB entry_quantity updated from {db_qty} to {alpaca_qty} to match authoritative Alpaca position.",
                    ),
                )
                return True

            self._with_cursor(_correct_quantity)
            logger.warning(
                f"[POSITION_DRIFT] {symbol}: corrected DB quantity {db_qty} '' {alpaca_qty} (Alpaca source of truth)"
            )

            from algo.reporting import notify

            try:
                notify(
                    severity="warning",
                    title="Position Quantity Corrected",
                    message=f"{symbol}: Corrected quantity {db_qty} '' {alpaca_qty} to match Alpaca after partial fill.",
                    symbol=symbol,
                    details={
                        "symbol": symbol,
                        "db_quantity": db_qty,
                        "alpaca_quantity": alpaca_qty,
                    },
                )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"Failed to send position correction alert: {e}")

            return {
                "valid": False,
                "db_quantity": db_qty,
                "alpaca_quantity": alpaca_qty,
                "corrected": True,
                "message": f"{symbol}: partial fill detected and corrected ({db_qty} '' {alpaca_qty})",
            }

        except requests.RequestException as e:
            logger.error(f"[POSITION_VALIDATION] Failed to validate {symbol}: {e}")
            return {
                "valid": False,
                "db_quantity": None,
                "alpaca_quantity": None,
                "corrected": False,
                "message": f"Alpaca connection error: {e}",
            }

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
