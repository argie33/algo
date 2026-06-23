#!/usr/bin/env python3
"""Exit trade execution handler extracted from TradeExecutor.

Handles:
- Exit condition validation
- Alpaca exit order submission
- Stop-raise-only operations
- Position and trade record updates
- P&L calculations (dollar and percent)
- R-multiple calculations against actual stop loss
- Partial vs full exit logic with transaction safety
- Exit notifications
"""

import json
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from algo.reporting import TradeNotificationService
from algo.trading.exceptions import (
    AuditLogError,
    DatabaseError,
    NotificationError,
    TradingError,
)
from utils.trading import PositionStatus

logger = logging.getLogger(__name__)


class ExitHandler:
    """Handles exit trade execution logic with transaction safety guarantees."""

    def __init__(self, context: Any) -> None:
        """Initialize with HandlerContext for access to dependencies (not whole executor)."""
        self.context = context
        self.config = context.config

    def execute_exit(
        self,
        trade_id: int,
        exit_price: float | None,
        exit_reason: str,
        exit_fraction: float = 1.0,
        exit_stage: str | None = None,
        new_stop_price: float | None = None,
        cur: Any | None = None,
    ) -> dict[str, Any]:
        """Exit all or part of a position with guaranteed transaction atomicity.

        Args:
            trade_id: trade to exit
            exit_price: execution price for the exit (must be > 0; None when exit_fraction=0)
            exit_reason: reason text (logged in algo_trades + algo_audit_log)
            exit_fraction: 0 = stop-raise-only (no exit order); 0 < f <= 1 for partial/full exits
            exit_stage: optional 'target_1' | 'target_2' | 'target_3' | 'stop' | 'time' | 'distribution'
            new_stop_price: if provided, raise the stop on the residual shares (trailing stop)
            cur: Optional existing cursor (for transactional batching). If None, opens own context.

        Returns: { success, trade_id, shares_exited, profit_loss_dollars, profit_loss_pct, message }

        TRANSACTION SAFETY GUARANTEES:
        - All updates (algo_trades, algo_positions, audit log) are atomic: all succeed or all rollback
        - Trade rows are locked (FOR UPDATE) to prevent concurrent modifications
        - Position rows are locked (FOR UPDATE OF p) to prevent concurrent modifications
        - After each critical update, rowcount is verified (must equal 1) to detect lost updates
        - After position update, position state is re-fetched and validated for consistency
        - If any update fails, the entire transaction is rolled back, preventing orphaned state
        - Audit log failure causes transaction rollback (data integrity > temporary logging gap)

        If cur is provided (from exit_engine.py), all operations join the parent transaction.
        If cur is None, each operation opens its own transaction (backward compatibility).
        """
        # Stop-raise-only path: raise stop without exiting shares
        if exit_fraction == 0:
            return self._raise_stop_only(trade_id, new_stop_price, cur)

        # Validate exit parameters
        validation_error = self._validate_exit_params(exit_fraction, exit_price)
        if validation_error:
            return validation_error

        # After validation, we know exit_price is a valid float > 0
        validated_exit_price = float(exit_price)  # type: ignore[arg-type]

        # Main exit execution with transaction safety
        try:
            if cur is not None:
                return self._execute_exit(
                    cur,
                    trade_id,
                    validated_exit_price,
                    exit_reason,
                    exit_fraction,
                    exit_stage,
                    new_stop_price,
                )
            else:
                result = self.context._with_cursor(
                    lambda c: self._execute_exit(
                        c,
                        trade_id,
                        validated_exit_price,
                        exit_reason,
                        exit_fraction,
                        exit_stage,
                        new_stop_price,
                    ),
                    acquire_locks=True,
                )
                return result  # type: ignore[no-any-return]
        except AuditLogError as e:
            logger.critical(f"Audit log failure during exit (data integrity risk): {e}")
            return {"success": False, "message": f"Audit log failure: {e}"}
        except DatabaseError as e:
            logger.error(f"Database error during trade exit: {e}")
            return {"success": False, "message": f"Database error: {e}"}
        except TradingError as e:
            logger.error(f"Trading error during exit: {type(e).__name__}: {e}")
            return {"success": False, "message": str(e)}
        except Exception as e:
            logger.exception(f"Unexpected error during trade exit: {type(e).__name__}: {e}")
            return {
                "success": False,
                "message": f"Unexpected error: {type(e).__name__}",
            }

    def _raise_stop_only(self, trade_id: int, new_stop_price: float | None, cur: Any | None) -> dict[str, Any]:
        """Raise stop on residual position without exiting shares."""
        if new_stop_price is None:
            return {
                "success": False,
                "message": "stop-raise-only (fraction=0) requires new_stop_price",
            }

        def _raise_stop(cursor: Any) -> dict[str, Any]:
            cursor.execute(
                """UPDATE algo_positions p
                   SET current_stop_price = %s
                   FROM algo_trades t
                   WHERE t.trade_id = ANY(p.trade_ids_arr)
                     AND t.trade_id = %s
                     AND p.status = %s
                     AND %s > COALESCE(p.current_stop_price, 0)""",
                (
                    new_stop_price,
                    trade_id,
                    PositionStatus.OPEN.value,
                    new_stop_price,
                ),
            )
            updated = cursor.rowcount > 0
            return {
                "success": True,
                "message": (
                    f"Stop raised to ${new_stop_price:.2f}"
                    if updated
                    else f"Stop already at or above ${new_stop_price:.2f} (no-op)"
                ),
            }

        try:
            if cur is not None:
                return _raise_stop(cur)
            else:
                return self.context._with_cursor(_raise_stop)  # type: ignore[no-any-return]
        except DatabaseError as e:
            logger.error(f"Database error raising stop: {e}")
            return {"success": False, "message": f"Database error: {e}"}
        except Exception as e:
            logger.error(f"Unexpected error raising stop: {type(e).__name__}: {e}")
            return {"success": False, "message": f"Stop raise failed: {e}"}

    def _validate_exit_params(self, exit_fraction: float, exit_price: float | None) -> dict[str, Any] | None:
        """Validate exit parameters. Returns error dict if invalid, None if valid."""
        if not (0 < exit_fraction <= 1.0):
            return {
                "success": False,
                "message": f"Invalid exit_fraction {exit_fraction}",
            }

        if not exit_price or exit_price <= 0:
            return {
                "success": False,
                "message": f"Invalid exit price: {exit_price} (must be > 0)",
            }

        return None

    def _execute_exit(
        self,
        cur: Any,
        trade_id: int,
        exit_price: float,
        exit_reason: str,
        exit_fraction: float,
        exit_stage: str | None,
        new_stop_price: float | None,
    ) -> dict[str, Any]:
        """Execute the core exit transaction with all safety guards."""
        # TRANSACTION GUARD 1: Verify trade is not already closed (idempotency)
        cur.execute(
            """SELECT status FROM algo_trades WHERE trade_id = %s FOR UPDATE""",
            (trade_id,),
        )
        trade_status_row = cur.fetchone()
        if trade_status_row and trade_status_row[0] == "closed":
            return {
                "success": False,
                "message": f"Trade {trade_id} is already closed (idempotency guard)",
                "duplicate": True,
            }

        # TRANSACTION GUARD 2: Fetch all trade and position data with row locks
        cur.execute(
            """SELECT t.symbol, t.entry_price, t.entry_quantity, t.stop_loss_price,
                       t.alpaca_order_id,
                       p.position_id, p.quantity, p.target_levels_hit, p.status
                FROM algo_trades t
                LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.trade_id = %s FOR UPDATE OF t, p""",
            (trade_id,),
        )
        row = cur.fetchone()
        if row is None:
            return {"success": False, "message": f"Trade {trade_id} not found"}

        (
            symbol,
            entry_price,
            entry_qty,
            stop_loss_price,
            alpaca_order_id,
            position_id,
            current_qty,
            _target_hits,
            position_status,
        ) = row

        entry_price = float(entry_price)
        entry_qty = int(entry_qty)
        stop_loss_price = float(stop_loss_price)
        current_qty = int(current_qty) if current_qty else 0

        if position_status == "closed":
            return {
                "success": False,
                "message": "Position already closed (idempotency guard)",
                "duplicate": True,
            }

        if current_qty <= 0 and not position_id:
            return {"success": False, "message": f"No open position for {trade_id}"}

        # Calculate shares to exit
        current_qty_dec = Decimal(str(current_qty))
        exit_frac_dec = Decimal(str(exit_fraction))
        shares_to_exit_dec = (current_qty_dec * exit_frac_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        shares_to_exit_dec = max(Decimal("0.01"), shares_to_exit_dec)
        shares_to_exit_dec = min(shares_to_exit_dec, current_qty_dec)
        shares_to_exit = float(float(shares_to_exit_dec))
        full_exit = shares_to_exit >= current_qty

        # Cancel bracket orders on full exit
        if full_exit and alpaca_order_id:
            cancel_result = self.context._cancel_bracket_orders(alpaca_order_id)
            if not cancel_result.get("success"):
                logger.warning(
                    f"Failed to cancel bracket for {trade_id}: {cancel_result.get('message', 'Unknown error')}"
                )

        # Execute exit order (if not review/paper mode)
        execution_mode = self.context.execution_mode
        actual_fill_price = None
        exit_order_result = {"success": False, "message": "No order sent"}
        is_estimated_price = True

        if execution_mode == "auto":
            exit_order_result = self.context._send_alpaca_exit(symbol, shares_to_exit)
            if exit_order_result.get("success"):
                actual_fill_price = exit_order_result["filled_price"] if "filled_price" in exit_order_result else None
                is_estimated_price = False
            else:
                try:
                    from algo.reporting import notify

                    notify(
                        "critical",
                        title=f"EXIT ORDER FAILED: {symbol}",
                        message=f"Trade {trade_id}: Failed to exit {shares_to_exit}sh. {exit_order_result['message'] if 'message' in exit_order_result else 'Unknown error'}",
                    )
                except NotificationError as e:
                    logger.warning(f"Failed to send exit failure alert (non-blocking): {e}")
                return {
                    "success": False,
                    "message": f"Exit order failed: {exit_order_result.get('message', 'Unknown error')}",
                }

        final_exit_price = actual_fill_price if actual_fill_price else exit_price

        # Validate prices
        if final_exit_price <= 0:
            logger.warning(f"Invalid exit price {final_exit_price} for {symbol}")
            return {"success": False, "message": f"Invalid exit price for {trade_id}"}

        if entry_price <= 0:
            logger.warning(f"Invalid entry price {entry_price} for {symbol}")
            return {"success": False, "message": f"Invalid entry price for {trade_id}"}

        # Calculate P&L metrics
        risk_per_share = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
        r_multiple = (
            float((Decimal(str(final_exit_price)) - Decimal(str(entry_price))) / risk_per_share)
            if risk_per_share > 0
            else 0.0
        )
        pnl_per_share = Decimal(str(final_exit_price)) - Decimal(str(entry_price))
        pnl_dollars = float((pnl_per_share * Decimal(str(shares_to_exit))).quantize(Decimal("0.01"), ROUND_HALF_UP))
        pnl_pct = (
            float((pnl_per_share / Decimal(str(entry_price)) * Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP))
            if entry_price > 0
            else 0.0
        )

        # Validate P&L calculations for NaN and invalid types
        if not isinstance(pnl_dollars, (int, float)):
            raise ValueError(f"P&L dollars calculation produced invalid type: {type(pnl_dollars)}")
        if isinstance(pnl_dollars, float) and pnl_dollars != pnl_dollars:  # NaN check
            raise ValueError(
                f"P&L dollars calculation produced NaN; check price={final_exit_price} "
                f"and quantity={shares_to_exit} for zero or invalid values"
            )

        if not isinstance(pnl_pct, (int, float)):
            raise ValueError(f"P&L percent calculation produced invalid type: {type(pnl_pct)}")
        if isinstance(pnl_pct, float) and pnl_pct != pnl_pct:  # NaN check
            raise ValueError(f"P&L percent calculation produced NaN; check entry_price={entry_price} for zero value")

        # TRANSACTION GUARD 3: Update algo_trades
        if full_exit:
            estimated_price = exit_price if is_estimated_price else None
            cur.execute(
                """UPDATE algo_trades
                    SET exit_date = CURRENT_DATE,
                        exit_time = CURRENT_TIMESTAMP,
                        exit_price = %s,
                        exit_reason = %s,
                        exit_r_multiple = %s,
                        profit_loss_dollars = %s,
                        profit_loss_pct = %s,
                        estimated_exit_price = %s,
                        status = 'closed'
                    WHERE trade_id = %s""",
                (
                    final_exit_price,
                    exit_reason,
                    r_multiple,
                    pnl_dollars,
                    pnl_pct,
                    estimated_price,
                    trade_id,
                ),
            )
            if cur.rowcount != 1:
                raise DatabaseError(f"Trade update failed: expected 1 row updated, got {cur.rowcount}")
        else:
            cur.execute(
                """UPDATE algo_trades
                    SET partial_exits_log = COALESCE(partial_exits_log, '') ||
                            CASE WHEN partial_exits_log IS NULL OR partial_exits_log = '' THEN '' ELSE '; ' END ||
                            %s,
                        partial_exit_count = partial_exit_count + 1,
                        last_partial_exit_date = CURRENT_DATE,
                        status = 'open'
                    WHERE trade_id = %s""",
                (
                    f"{shares_to_exit}sh @ ${final_exit_price:.2f} ({exit_reason}, {r_multiple:.2f}R)",
                    trade_id,
                ),
            )
            if cur.rowcount != 1:
                raise DatabaseError(f"Partial exit log update failed: expected 1 row updated, got {cur.rowcount}")

        # Calculate new position quantity
        current_qty_dec = Decimal(str(current_qty))
        shares_exited_dec = Decimal(str(shares_to_exit))
        new_qty_dec = current_qty_dec - shares_exited_dec
        new_qty = float(float(new_qty_dec))

        # TRANSACTION GUARD 4: Update position with safety checks
        effective_stop = new_stop_price if new_stop_price is not None else stop_loss_price
        update_success, update_error = self.context._update_position_with_retry(
            cur=cur,
            position_id=position_id,
            new_qty=new_qty,
            new_stop_price=effective_stop,
            full_exit=full_exit or new_qty <= 0,
            exit_stage=exit_stage,
        )

        if not update_success:
            raise DatabaseError(update_error or "Position update failed during exit")

        # TRANSACTION GUARD 5: Verify position state consistency after update
        cur.execute(
            """SELECT quantity, status FROM algo_positions WHERE position_id = %s""",
            (position_id,),
        )
        verify_row = cur.fetchone()
        if verify_row:
            final_qty = verify_row[0]
            final_status = verify_row[1]
            if full_exit and final_status != "closed":
                raise DatabaseError(
                    f"Position consistency error: full exit executed but position status is '{final_status}' (expected 'closed')"
                )
            if not full_exit and (final_status != "open" or final_qty != new_qty):
                raise DatabaseError(
                    f"Position consistency error: partial exit expected {new_qty} shares and 'open' status, "
                    f"got {final_qty} shares and '{final_status}'"
                )

        # TRANSACTION GUARD 6: Audit log is part of atomic transaction
        try:
            cur.execute(
                """INSERT INTO algo_audit_log (action_type, symbol, action_date,
                                                details, actor, status, created_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, CURRENT_TIMESTAMP)""",
                (
                    f"exit_{exit_stage or 'manual'}",
                    symbol,
                    json.dumps(
                        {
                            "trade_id": trade_id,
                            "shares_exited": shares_to_exit,
                            "exit_price": float(final_exit_price),
                            "r_multiple": float(r_multiple),
                            "pnl_dollars": float(pnl_dollars),
                            "pnl_pct": float(pnl_pct),
                            "reason": exit_reason,
                            "full_exit": full_exit,
                        }
                    ),
                    "algo_executor",
                    "success",
                ),
            )
            if cur.rowcount != 1:
                raise DatabaseError(f"Audit log insert failed: expected 1 row, got {cur.rowcount}")
        except Exception as audit_e:
            logger.critical(
                f"[AUDIT_FAILURE] Could not audit log trade exit {trade_id}: {type(audit_e).__name__}: {audit_e}"
            )
            raise AuditLogError(f"Failed to log trade exit: {audit_e}") from audit_e

        # Send notification (non-blocking failure)
        try:
            notif_service = TradeNotificationService()
            notif_service._send_notification(
                subject=f"EXIT: {symbol}",
                message=f"{shares_to_exit:.2f}sh @ ${final_exit_price:.2f} ({pnl_pct:+.2f}%, {r_multiple:+.2f}R) - {exit_reason}",
                kind="trade_exit",
                severity="info" if pnl_dollars > 0 else "warning",
                symbol=symbol,
                details={
                    "exit_price": final_exit_price,
                    "shares": shares_to_exit,
                    "pnl": f"{pnl_dollars:+.2f}",
                    "pnl_pct": pnl_pct,
                    "r_multiple": r_multiple,
                    "reason": exit_reason,
                    "trade_id": trade_id,
                },
            )
        except NotificationError as notif_e:
            logger.error(f"Critical: Failed to send exit notification for {symbol}: {notif_e}")
            raise RuntimeError(f"Critical: Exit notification failed for {symbol}") from notif_e

        return {
            "success": True,
            "trade_id": trade_id,
            "shares_exited": shares_to_exit,
            "profit_loss_dollars": pnl_dollars,
            "profit_loss_pct": pnl_pct,
            "r_multiple": r_multiple,
            "full_exit": full_exit,
            "message": (
                f"Exited {shares_to_exit}sh of {symbol} @ ${final_exit_price:.2f} ({pnl_pct:+.2f}%, {r_multiple:+.2f}R)"
            ),
        }
