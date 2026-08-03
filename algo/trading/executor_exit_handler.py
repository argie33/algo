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

from __future__ import annotations

import json
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, cast

from psycopg2.extensions import cursor as PsycopgCursor

if TYPE_CHECKING:
    from algo.trading.handler_context import HandlerContext

from algo.reporting import TradeNotificationService
from algo.trading.exceptions import (
    AuditLogError,
    DatabaseError,
    DataUnavailableError,
    NotificationError,
    TradingError,
)
from utils.trading import PositionStatus

logger = logging.getLogger(__name__)


class ExitHandler:
    """Handles exit trade execution logic with transaction safety guarantees."""

    def __init__(self, context: HandlerContext) -> None:
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
        cur: PsycopgCursor[Any] | None = None,
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

        # After validation, we know exit_price is a valid float > 0. A plain `assert`
        # is stripped entirely under `python -O` - not currently used in this repo's
        # deployment, but load-bearing financial safety code shouldn't depend on that
        # staying true, same reasoning already applied to PositionSizer's equivalent
        # checks (raise ValueError, not assert).
        if exit_price is None or exit_price <= 0:
            raise ValueError(f"Exit price must be > 0 after validation, got {exit_price!r}")
        validated_exit_price = float(exit_price)
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
                return cast(dict[str, Any], result)
        except AuditLogError as e:
            logger.critical(f"Audit log failure during exit (data integrity risk): {e}")
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": f"Audit log failure: {e}",
            }
        except DatabaseError as e:
            logger.error(f"Database error during trade exit: {e}")
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": f"Database error: {e}",
            }
        except TradingError as e:
            logger.error(f"Trading error during exit: {type(e).__name__}: {e}")
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": str(e),
            }
        except Exception as e:
            logger.exception(f"Unexpected error during trade exit: {type(e).__name__}: {e}")
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": f"Unexpected error: {type(e).__name__}",
            }

    def _raise_stop_only(
        self, trade_id: int, new_stop_price: float | None, cur: PsycopgCursor[Any] | None
    ) -> dict[str, Any]:
        """Raise stop on residual position without exiting shares."""
        if new_stop_price is None:
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": "stop-raise-only (fraction=0) requires new_stop_price",
            }

        def _raise_stop(cursor: PsycopgCursor[Any]) -> dict[str, Any]:
            # Validate position has existing stop price (cannot raise NULL stop)
            cursor.execute(
                """SELECT p.current_stop_price FROM algo_positions p
                   JOIN algo_trades t ON t.trade_id = ANY(p.trade_ids_arr)
                   WHERE t.trade_id = %s
                     AND p.status = %s
                   LIMIT 1""",
                (trade_id, PositionStatus.OPEN.value),
            )
            existing_stop = cursor.fetchone()
            if not existing_stop or existing_stop[0] is None:
                return {
                    "success": False,
                    "trade_id": trade_id,
                    "shares_exited": 0,
                    "profit_loss_dollars": None,
                    "profit_loss_pct": None,
                    "r_multiple": None,
                    "full_exit": False,
                    "is_estimated_price": False,
                    "message": "Cannot raise stop: position has no existing stop price (position state incomplete). "
                    "Initialize stop price explicitly before raising.",
                }
            if new_stop_price <= existing_stop[0]:
                return {
                    "success": False,
                    "trade_id": trade_id,
                    "shares_exited": 0,
                    "profit_loss_dollars": None,
                    "profit_loss_pct": None,
                    "r_multiple": None,
                    "full_exit": False,
                    "is_estimated_price": False,
                    "message": f"Stop raise rejected: new stop ${new_stop_price:.2f} not above existing ${existing_stop[0]:.2f}",
                }

            cursor.execute(
                """UPDATE algo_positions p
                   SET current_stop_price = %s
                   FROM algo_trades t
                   WHERE t.trade_id = ANY(p.trade_ids_arr)
                     AND t.trade_id = %s
                     AND p.status = %s
                     AND p.current_stop_price IS NOT NULL
                     AND %s > p.current_stop_price""",
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
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
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
                return cast(dict[str, Any], self.context._with_cursor(_raise_stop))
        except DatabaseError as e:
            logger.error(f"Database error raising stop: {e}")
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": f"Database error: {e}",
            }
        except Exception as e:
            logger.error(f"Unexpected error raising stop: {type(e).__name__}: {e}")
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": f"Stop raise failed: {e}",
            }

    def _validate_exit_params(self, exit_fraction: float, exit_price: float | None) -> dict[str, Any] | None:
        if not (0 < exit_fraction <= 1.0):
            return {
                "success": False,
                "trade_id": None,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": f"Invalid exit_fraction {exit_fraction}",
            }

        if exit_price is None or exit_price <= 0:
            return {
                "success": False,
                "trade_id": None,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": f"Invalid exit price: {exit_price} (must be > 0)",
            }

        logger.debug(f"[EXIT_HANDLER] Exit parameters valid (fraction={exit_fraction}, price={exit_price})")
        return None

    def _check_trade_not_already_closed(self, cur: PsycopgCursor[Any], trade_id: int) -> dict[str, Any] | None:
        """Guard 1: Verify trade is not already closed (idempotency check).

        Returns:
            Error dict if trade already closed, None if guard passes.
        """
        cur.execute(
            """SELECT status FROM algo_trades WHERE trade_id = %s FOR UPDATE""",
            (trade_id,),
        )
        trade_status_row = cur.fetchone()
        if trade_status_row and trade_status_row[0] == "closed":
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": f"Trade {trade_id} is already closed (idempotency guard)",
                "duplicate": True,
            }
        return None

    def _fetch_and_lock_trade_data(self, cur: PsycopgCursor[Any], trade_id: int) -> tuple[Any, ...]:
        """Guard 2: Fetch all trade and position data with row locks.

        Lock algo_trades (t) only - PostgreSQL forbids FOR UPDATE on nullable side
        of LEFT JOIN (p may be NULL if trade has no position yet).

        Returns:
            Tuple of (symbol, entry_price, entry_qty, stop_loss_price, alpaca_order_id,
                     position_id, current_qty, target_hits, position_status)

        Raises:
            RuntimeError: If trade not found in database
        """
        cur.execute(
            """SELECT t.symbol, t.entry_price, t.entry_quantity, t.stop_loss_price,
                       t.alpaca_order_id,
                       p.position_id, p.quantity, p.target_levels_hit, p.status
                FROM algo_trades t
                LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.trade_id = %s FOR UPDATE OF t""",
            (trade_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"[EXECUTOR_EXIT] Trade {trade_id} not found in database - "
                "cannot execute exit for non-existent trade. Check if trade was properly recorded."
            )
        return tuple(row)

    def _validate_and_convert_trade_data(
        self, cur: PsycopgCursor[Any], trade_id: int, row: tuple[Any, ...]
    ) -> tuple[str, float, int, float, str, int | None, float, int, str]:
        """Validate and type-convert fetched trade data.

        Args:
            cur: Database cursor for locking positions
            trade_id: Trade ID (for error messages)
            row: Tuple from _fetch_and_lock_trade_data

        Returns:
            Tuple of (symbol, entry_price, entry_qty, stop_loss_price, alpaca_order_id,
                     position_id, current_qty, target_hits, position_status)

        Raises:
            DataUnavailableError: If position quantity unavailable
        """
        (
            symbol,
            entry_price,
            entry_qty,
            stop_loss_price,
            alpaca_order_id,
            position_id,
            current_qty,
            target_hits,
            position_status,
        ) = row

        # Lock algo_positions separately now that we have the position_id
        if position_id is not None:
            cur.execute(
                "SELECT 1 FROM algo_positions WHERE position_id = %s FOR UPDATE",
                (position_id,),
            )

        entry_price_f = float(entry_price)
        entry_qty_i = int(entry_qty)
        stop_loss_price_f = float(stop_loss_price)

        if current_qty is None:
            raise DataUnavailableError(
                f"Position quantity unavailable for trade {trade_id} (symbol {symbol}). "
                f"Cannot execute exit without known current position size."
            )
        current_qty_f = float(current_qty)  # float preserves fractional shares

        return (
            symbol,
            entry_price_f,
            entry_qty_i,
            stop_loss_price_f,
            alpaca_order_id,
            position_id,
            current_qty_f,
            target_hits,
            position_status,
        )

    # Ordered (checked top-down) prefix match against exit_engine.py's actual reason strings
    # (see exit_engine.py's "reason" fields - these are the only exit_reason values this
    # system's exit logic ever produces). Bucketed into stable rule names for
    # algo_exit_rules_distribution, which stores a free-text exit_reason column alongside
    # this categorical one specifically so the dashboard can group "how did positions exit"
    # without doing text matching downstream.
    _EXIT_RULE_PATTERNS: tuple[tuple[str, str], ...] = (
        ("STOP hit", "stop_loss"),
        ("Minervini trend break", "trend_break"),
        ("RS line broke", "relative_strength_break"),
        ("TIME exit", "time_exit"),
        ("T1 exit", "profit_target_t1"),
        ("T2 exit", "profit_target_t2"),
        ("T3 target hit", "profit_target_t3"),
        ("Chandelier", "trailing_stop"),
        ("TD Combo", "td_exhaustion"),
        ("TD Sequential", "td_exhaustion"),
        ("First Red Day", "first_red_day"),
        ("Climax run exhaustion", "climax_exhaustion"),
        ("Market distribution", "distribution_days"),
        ("Minimum holding period", "min_holding_period"),
    )

    @classmethod
    def _classify_exit_rule(cls, exit_reason: str) -> str:
        """Bucket a free-text exit_reason into a stable exit_rule category. Falls back to
        "other" for reasons that don't match a known pattern (e.g. manual/API-triggered
        exits) rather than guessing - "other" is itself informative in the distribution."""
        for prefix, rule in cls._EXIT_RULE_PATTERNS:
            if prefix in exit_reason:
                return rule
        return "other"

    def _calculate_exit_shares(self, current_qty: float, exit_fraction: float) -> tuple[float, bool]:
        """Calculate number of shares to exit with proper rounding.

        Args:
            current_qty: Current position size
            exit_fraction: Fraction of position to exit (0 < x <= 1)

        Returns:
            Tuple of (shares_to_exit, is_full_exit)
        """
        current_qty_dec = Decimal(str(current_qty))
        exit_frac_dec = Decimal(str(exit_fraction))
        shares_to_exit_dec = (current_qty_dec * exit_frac_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        shares_to_exit_dec = max(Decimal("0.01"), shares_to_exit_dec)
        shares_to_exit_dec = min(shares_to_exit_dec, current_qty_dec)
        shares_to_exit = float(shares_to_exit_dec)
        full_exit = shares_to_exit >= current_qty

        return shares_to_exit, full_exit

    def _compute_cumulative_pnl(
        self,
        cur: PsycopgCursor[Any],
        trade_id: int,
        symbol: str,
        pnl_dollars: float,
        pnl_pct: float,
        r_multiple: float,
        entry_price: float,
        entry_qty: int,
        risk_per_share: Decimal,
        full_exit: bool,
        is_estimated_price: bool,
    ) -> tuple[float, float, float]:
        """Return (pnl_dollars, pnl_pct, r_multiple), summed across every leg of a
        multi-leg exit when this call is the final leg.

        CRITICAL (2026-07-21 financial-integrity audit): a position closed via multiple
        partial exits (e.g. T1/T2 profit-taking before a final stop/target exit) previously
        had algo_trades.profit_loss_dollars/pct/exit_r_multiple set from ONLY the final
        leg's shares_to_exit - the remaining shares at that point, not the original position
        size. Earlier partial exits log their own pnl_dollars into algo_audit_log (structured
        JSON, one row per leg) but nothing ever aggregated them before this fix, so the
        trade-level total silently discarded every dollar realized on the earlier legs.
        Concrete example: a 100-share position that takes 40sh profit at T1 (+$200) then
        closes the remaining 60sh at breakeven would have recorded profit_loss_dollars=$0
        for the whole trade pre-fix, when the true realized total is +$200.

        For a partial exit (full_exit=False) or an unreconciled estimated fill, there is no
        final trade-level total to report yet - returns the single-leg values unchanged.
        """
        if not (full_exit and not is_estimated_price):
            return pnl_dollars, pnl_pct, r_multiple

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
        prior_partial_pnl_dec = Decimal(str(prior_partial_pnl_row[0])) if prior_partial_pnl_row else Decimal(0)
        if prior_partial_pnl_dec == 0:
            return pnl_dollars, pnl_pct, r_multiple

        cumulative_pnl_dollars_dec = (prior_partial_pnl_dec + Decimal(str(pnl_dollars))).quantize(
            Decimal("0.01"), ROUND_HALF_UP
        )
        entry_qty_dec = Decimal(str(entry_qty))
        original_cost_basis = Decimal(str(entry_price)) * entry_qty_dec
        original_risk_dollars = risk_per_share * entry_qty_dec
        cumulative_pnl_dollars = float(cumulative_pnl_dollars_dec)
        cumulative_pnl_pct = float(
            (cumulative_pnl_dollars_dec / original_cost_basis * Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        )
        cumulative_r_multiple = float(
            (cumulative_pnl_dollars_dec / original_risk_dollars).quantize(Decimal("0.01"), ROUND_HALF_UP)
        )
        logger.info(
            f"[MULTI_LEG_EXIT] {symbol} trade {trade_id}: cumulative P&L across all legs "
            f"${cumulative_pnl_dollars:.2f} (prior partial legs: ${float(prior_partial_pnl_dec):.2f}, "
            f"final leg: ${pnl_dollars:.2f})"
        )
        return cumulative_pnl_dollars, cumulative_pnl_pct, cumulative_r_multiple

    def _execute_exit(  # noqa: C901
        self,
        cur: PsycopgCursor[Any],
        trade_id: int,
        exit_price: float,
        exit_reason: str,
        exit_fraction: float,
        exit_stage: str | None,
        new_stop_price: float | None,
    ) -> dict[str, Any]:
        """Execute the core exit transaction with all safety guards.

        Orchestrates exit flow: guard checks → data fetching → share calculation →
        bracket cancellation → order submission → P&L recording.
        """
        # GUARD 1: Check if trade already closed (idempotency)
        guard1_error = self._check_trade_not_already_closed(cur, trade_id)
        if guard1_error:
            return guard1_error

        # GUARD 2: Fetch and lock trade/position data
        row = self._fetch_and_lock_trade_data(cur, trade_id)

        # Validate and convert data types
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
        ) = self._validate_and_convert_trade_data(cur, trade_id, row)

        # GUARD 3: Check position status
        if position_status == "closed":
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": "Position already closed (idempotency guard)",
                "duplicate": True,
            }

        if current_qty <= 0 and not position_id:
            return {
                "success": False,
                "trade_id": trade_id,
                "shares_exited": 0,
                "profit_loss_dollars": None,
                "profit_loss_pct": None,
                "r_multiple": None,
                "full_exit": False,
                "is_estimated_price": False,
                "message": f"No open position for {trade_id}",
            }

        # Calculate shares to exit
        shares_to_exit, full_exit = self._calculate_exit_shares(current_qty, exit_fraction)

        # Cancel bracket orders on full exit
        if full_exit and alpaca_order_id:
            cancel_result = self.context._cancel_bracket_orders(alpaca_order_id)
            if "success" not in cancel_result:
                raise RuntimeError(
                    f"Cancel bracket result missing 'success' field. "
                    f"Available keys: {list(cancel_result.keys())}. "
                    f"Cannot determine if bracket was cancelled."
                )
            if not cancel_result["success"]:
                # Explicit message handling - fail if missing instead of defaulting to "Unknown error"
                message = cancel_result.get("message")
                if not message:
                    logger.error(f"[EXIT_HANDLER] Cancel result missing error message for {trade_id}")
                    message = "Bracket cancellation failed (no error message provided)"
                logger.warning(f"Failed to cancel bracket for {trade_id}: {message}")

        # Execute exit order (if not review/paper mode)
        execution_mode = self.context.execution_mode
        actual_fill_price = None
        exit_order_result = {"success": False, "message": "No order sent"}
        # CRITICAL FIX: only "auto" mode has genuine fill-price uncertainty (a submitted
        # order hasn't been confirmed by the broker yet - see is_estimated_price=False
        # explicitly set below once a fill is confirmed, or the early-return with
        # profit_loss_dollars=None if the order fails). Paper/review mode never submits
        # a real order at all - the `exit_price` this function was called with (the exit
        # engine's live quote at evaluation time) IS the final, deterministic simulated
        # fill price, not a pending estimate. Previously this was unconditionally True,
        # so every paper-mode exit permanently recorded profit_loss_dollars=NULL (nothing
        # ever reconciles a paper "estimate" into a confirmed price - that mechanism only
        # exists for auto mode's real broker fill). Live-reproduced 2026-07-27: 9 stop-loss
        # exits in paper mode all recorded NULL P&L, then reconciliation.py's realized-P&L
        # query found closed_count=9 but SUM(profit_loss_dollars) NULL and raised
        # "data corruption detected", permanently halting all further trading the moment
        # any paper position closed.
        is_estimated_price = execution_mode == "auto"

        if execution_mode == "auto":
            exit_order_result = self.context._send_alpaca_exit(symbol, shares_to_exit, trade_id)

            # Validate result structure
            if "success" not in exit_order_result:
                raise RuntimeError(
                    f"Exit order result missing 'success' field. "
                    f"Available keys: {list(exit_order_result.keys())}. "
                    f"Cannot determine if exit order succeeded."
                )

            if exit_order_result["success"]:
                actual_fill_price = exit_order_result.get("filled_price")
                if actual_fill_price is None:
                    # CRITICAL FIX: a submitted order with no fill price yet is a routine,
                    # documented broker response (see order_manager.py's
                    # _exit_result_from_order_data - "fill pending, will be reconciled"), NOT
                    # an error. By the time we get here the protective bracket may already be
                    # cancelled and a real sell may already be in flight at the broker - raising
                    # unwinds this whole transaction (no DB write at all) and leaves the
                    # position looking untouched/still fully protected in our own records while
                    # the broker has already acted. Instead, keep is_estimated_price=True (set
                    # above from execution_mode=="auto") and fall through to the
                    # PENDING_FILL_RECONCILIATION path below, which records the position closed
                    # with this evaluation-time quote as a placeholder and defers the real fill
                    # price/P&L to algo/infrastructure/reconciliation.py's
                    # resolve_local_pending_exits/audit_stale_estimated_prices on a later pass.
                    actual_fill_price = exit_price
                    logger.info(
                        f"[EXIT_HANDLER] {symbol}: exit order accepted, fill price pending - "
                        f"recording as PENDING_FILL_RECONCILIATION with estimated price ${exit_price}"
                    )
                else:
                    is_estimated_price = False

                    # CRITICAL: send_market_exit()'s response never includes the actual filled
                    # quantity (only filled_price) - so unlike the entry side (executor_entry_
                    # handler.py explicitly checks order_status == "partially_filled" and calls
                    # _get_order_filled_quantity to get the real fill amount), this exit path was
                    # blindly trusting shares_to_exit (the REQUESTED amount) as if it were always
                    # fully filled. A genuine partial fill on a sell order (illiquid/small-cap
                    # names - the liquidity_checks.py screen exists precisely because this system
                    # trades those - or a volatile market) would then record more shares exited
                    # than actually sold, permanently understating the real remaining position by
                    # the unfilled portion, with no reconciliation path to catch it since Phase 9
                    # only polls for a pending fill *price*, not a fill *quantity* mismatch.
                    # Verify against the broker directly, mirroring the entry-side pattern exactly.
                    # Only meaningful once the order is actually confirmed filled - a pending
                    # order (handled above) has no real filled quantity to verify yet.
                    exit_order_id = exit_order_result.get("order_id")
                    if exit_order_id:
                        verified_filled_qty = self.context._get_order_filled_quantity(exit_order_id)
                        if verified_filled_qty is not None and verified_filled_qty > 0:
                            if verified_filled_qty != shares_to_exit:
                                logger.warning(
                                    f"[EXIT_HANDLER] {symbol}: partial exit fill - requested "
                                    f"{shares_to_exit}sh, broker filled {verified_filled_qty}sh. "
                                    f"Using verified fill quantity."
                                )
                            shares_to_exit = verified_filled_qty
                            full_exit = shares_to_exit >= current_qty
            else:
                # Explicit message handling - log if missing instead of defaulting
                error_message = exit_order_result.get("message")
                if not error_message:
                    logger.error(f"[EXIT_HANDLER] Exit order result missing error message for {symbol}")
                    error_message = "Exit order failed (no error message provided)"
                try:
                    from algo.reporting import notify

                    notify(
                        "critical",
                        title=f"EXIT ORDER FAILED: {symbol}",
                        message=f"Trade {trade_id}: Failed to exit {shares_to_exit}sh. {error_message}",
                    )
                except NotificationError as e:
                    logger.warning(f"Failed to send exit failure alert (non-blocking): {e}")
                return {
                    "success": False,
                    "trade_id": trade_id,
                    "shares_exited": 0,
                    "profit_loss_dollars": None,
                    "profit_loss_pct": None,
                    "r_multiple": None,
                    "full_exit": False,
                    "is_estimated_price": False,
                    "message": f"Exit order failed: {error_message}",
                }

        # Determine final exit price with explicit fail-fast validation.
        #
        # CRITICAL FIX: this used to branch on `is_estimated_price` (now False for both
        # paper/review AND a confirmed auto-mode fill - see the field's new definition
        # above), which left paper/review mode matching neither branch and raising the
        # "should never happen" RuntimeError below on every single exit. Live-reproduced
        # 2026-07-27 immediately after the is_estimated_price fix. The actual question
        # here is "did we submit a real order," which is exactly what execution_mode
        # already answers - so branch on that directly instead.
        if execution_mode == "auto":
            # Auto mode only reaches here after a confirmed fill (an order failure
            # returns early above) - must use the actual price, never fall back.
            if actual_fill_price is None:
                raise DataUnavailableError(
                    f"[CRITICAL] Auto mode executed order but actual_fill_price is None for {symbol}. "
                    f"Logic error: execution succeeded but fill price unavailable. Cannot record exit."
                )
            final_exit_price = actual_fill_price
        else:
            # Paper/review mode - no real order was submitted; the exit engine's live
            # quote at evaluation time (exit_price) is the final, deterministic simulated
            # fill price.
            final_exit_price = exit_price

        # Validate prices - fail-fast instead of returning error dict
        if final_exit_price <= 0:
            raise ValueError(
                f"[INVALID_EXIT_PRICE] Exit price {final_exit_price} is invalid for {symbol}. "
                f"Cannot execute trade with zero or negative price. Check broker response or market data validity."
            )

        if entry_price <= 0:
            raise ValueError(
                f"[INVALID_ENTRY_PRICE] Entry price {entry_price} is invalid for {symbol}. "
                f"Cannot calculate P&L with zero or negative entry price. Check position data integrity."
            )

        # Calculate P&L metrics
        risk_per_share = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
        if risk_per_share <= 0:
            raise ValueError(
                f"[R_MULTIPLE CRITICAL] Invalid risk_per_share={risk_per_share} for {symbol}: "
                f"stop_loss_price ({stop_loss_price}) >= entry_price ({entry_price}). "
                f"Cannot compute R-multiple with invalid stop price. This indicates corrupted position data."
            )
        r_multiple = float((Decimal(str(final_exit_price)) - Decimal(str(entry_price))) / risk_per_share)
        pnl_per_share = Decimal(str(final_exit_price)) - Decimal(str(entry_price))
        pnl_dollars = float((pnl_per_share * Decimal(str(shares_to_exit))).quantize(Decimal("0.01"), ROUND_HALF_UP))
        pnl_pct = float(
            (pnl_per_share / Decimal(str(entry_price)) * Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP)
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

        # CRITICAL (2026-07-21 financial-integrity audit): for a multi-leg exit (position
        # closed via T1/T2 partial profit-taking before the final leg), pnl_dollars/pnl_pct/
        # r_multiple above reflect ONLY shares_to_exit for THIS call - the remaining shares
        # at final-exit time, not the original position size. See _compute_cumulative_pnl's
        # docstring for the full explanation and a concrete example of the corruption this
        # caused before the fix.
        cumulative_pnl_dollars, cumulative_pnl_pct, cumulative_r_multiple = self._compute_cumulative_pnl(
            cur,
            trade_id,
            symbol,
            pnl_dollars,
            pnl_pct,
            r_multiple,
            entry_price,
            entry_qty,
            risk_per_share,
            full_exit,
            is_estimated_price,
        )

        # TRANSACTION GUARD 3: Update algo_trades
        if full_exit:
            estimated_price = exit_price if is_estimated_price else None

            # CRITICAL: Do NOT store P&L calculated from estimated prices
            # P&L with synthetic prices corrupts circuit breaker decisions and performance metrics
            # Only store actual P&L after reconciliation with real fills
            if is_estimated_price:
                logger.warning(
                    f"[RECONCILIATION] Trade {trade_id} ({symbol}) marked closed with estimated exit price {exit_price}. "
                    f"P&L calculation deferred until reconciliation with actual broker fills. "
                    f"Status: PENDING_FILL_RECONCILIATION"
                )
                cur.execute(
                    """UPDATE algo_trades
                        SET exit_date = CURRENT_DATE,
                            exit_time = CURRENT_TIMESTAMP,
                            exit_price = %s,
                            exit_reason = %s,
                            estimated_exit_price = %s,
                            status = 'closed',
                            profit_loss_dollars = NULL,
                            profit_loss_pct = NULL,
                            exit_r_multiple = NULL,
                            trade_duration_days = CURRENT_DATE - entry_date,
                            pending_exit_client_order_id = NULL
                        WHERE trade_id = %s""",
                    (
                        final_exit_price,
                        exit_reason,
                        estimated_price,
                        trade_id,
                    ),
                )
            else:
                # Real fill: store actual P&L. Cumulative across all legs for a multi-leg
                # exit (see comment above) - equals pnl_dollars/pnl_pct/r_multiple unchanged
                # when there were no prior partial exits.
                cur.execute(
                    """UPDATE algo_trades
                        SET exit_date = CURRENT_DATE,
                            exit_time = CURRENT_TIMESTAMP,
                            exit_price = %s,
                            exit_reason = %s,
                            exit_r_multiple = %s,
                            profit_loss_dollars = %s,
                            profit_loss_pct = %s,
                            status = 'closed',
                            trade_duration_days = CURRENT_DATE - entry_date,
                            pending_exit_client_order_id = NULL
                        WHERE trade_id = %s""",
                    (
                        final_exit_price,
                        exit_reason,
                        cumulative_r_multiple,
                        cumulative_pnl_dollars,
                        cumulative_pnl_pct,
                        trade_id,
                    ),
                )
            trade_update_rowcount = cur.rowcount
            if trade_update_rowcount != 1:
                raise DatabaseError(f"Trade update failed: expected 1 row updated, got {trade_update_rowcount}")

            if not is_estimated_price:
                # algo_exit_rules_distribution's schema was added by migration but never
                # written to - it sat permanently empty, which made
                # lambda/api/routes/risk_dashboard.py's comprehensive risk dashboard 503
                # unconditionally (raises when the table has zero rows). Only recorded here
                # (real-fill P&L branch), not the estimated-price branch above, matching
                # this table's consumer expecting real, reconciled P&L - not a placeholder
                # pending fill-price confirmation. Part of the same transaction as the
                # algo_trades update above: a failure here rolls back the whole exit, same
                # as this function's other transaction-safety guarantees.
                cur.execute(
                    """INSERT INTO algo_exit_rules_distribution (
                        symbol, position_id, exit_rule, exit_reason,
                        entry_price, exit_price, pnl_dollars, pnl_pct, r_multiple
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        symbol,
                        position_id if position_id is not None else str(trade_id),
                        self._classify_exit_rule(exit_reason),
                        exit_reason,
                        float(entry_price),
                        final_exit_price,
                        pnl_dollars,
                        pnl_pct,
                        r_multiple,
                    ),
                )
        else:
            cur.execute(
                """UPDATE algo_trades
                    SET partial_exits_log = COALESCE(partial_exits_log, '') ||
                            CASE WHEN partial_exits_log IS NULL OR partial_exits_log = '' THEN '' ELSE '; ' END ||
                            %s,
                        partial_exit_count = partial_exit_count + 1,
                        last_partial_exit_date = CURRENT_DATE,
                        status = 'open',
                        pending_exit_client_order_id = NULL
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
        new_qty = float(new_qty_dec)

        # TRANSACTION GUARD 4: Update position with safety checks
        effective_stop = new_stop_price if new_stop_price is not None else stop_loss_price

        # When closing a position, pass P&L values to be persisted in algo_positions
        close_pnl_dollars = cumulative_pnl_dollars if (full_exit or new_qty <= 0) else None
        close_pnl_pct = cumulative_pnl_pct if (full_exit or new_qty <= 0) else None

        update_success, update_error = self.context._update_position_with_retry(
            cur=cur,
            position_id=position_id,
            new_qty=new_qty,
            new_stop_price=effective_stop,
            full_exit=full_exit or new_qty <= 0,
            exit_stage=exit_stage,
            pnl_dollars=close_pnl_dollars,
            pnl_pct=close_pnl_pct,
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
            # CRITICAL FIX: comparing the DB's Decimal directly against the Python float
            # `new_qty` false-positived on exact matches - a binary float can't represent
            # values like 4.87 exactly, so Decimal('4.8700') != 4.87 evaluates True even
            # though they're the same number. Live-reproduced 2026-07-27: 3 correct
            # partial exits raised "expected 4.87 shares... got 4.8700 shares" and were
            # counted as failures. Route both sides through Decimal(str(...)) - the string
            # form matches on decimal value, not binary float representation.
            if not full_exit and (
                final_status != "open" or Decimal(str(final_qty)) != Decimal(str(new_qty))
            ):
                raise DatabaseError(
                    f"Position consistency error: partial exit expected {new_qty} shares and 'open' status, "
                    f"got {final_qty} shares and '{final_status}'. "
                    f"This indicates the UPDATE WHERE quantity={current_qty} clause failed to match (optimistic lock failure) "
                    f"or another process modified the position between our calculation and verification. "
                    f"Check Phase 3 position monitor execution timing and advisory lock status."
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

        # Send notification (best-effort, must never fail the exit).
        #
        # CRITICAL FIX: by this point the exit is fully committed to this transaction's
        # cursor (algo_trades, algo_positions, algo_audit_log all updated above) and, in
        # auto mode, a REAL broker sell order has already filled - an irreversible,
        # already-happened event. This block used to `except NotificationError` and
        # re-raise as RuntimeError despite its own comment saying "non-blocking failure".
        # That except clause could never even match: TradeNotificationService._send_notification
        # / _save_notification raise bare RuntimeError (DB write failure) or whatever
        # exception AlertManager._send_email raises (e.g. SMTP errors) - never
        # NotificationError - so ANY notification hiccup propagated uncaught out of this
        # function, out of the `with DatabaseContext("write") as cur:` block in
        # _with_cursor, which rolls back on any exception. That rollback undid the
        # already-real broker exit's DB record (trade/position marked open again), while
        # execute_exit()'s own outer `except Exception` then swallowed the RuntimeError
        # into a plain `success: False` return - no crash, no halted status, just a
        # position that was actually closed at the broker but silently reverted to "open"
        # in the DB, with no operator signal beyond a generic exit-failure log line. Now
        # broadened to catch anything and only log - matching the stated "non-blocking"
        # design - so a notification delivery problem can never revert a real trade.
        try:
            notif_service = TradeNotificationService(config={"enabled": True})
            if is_estimated_price:
                message = f"{shares_to_exit:.2f}sh @ ${final_exit_price:.2f} (ESTIMATED) - {exit_reason} [P&L pending fill reconciliation]"
                severity = "info"
            else:
                message = f"{shares_to_exit:.2f}sh @ ${final_exit_price:.2f} ({pnl_pct:+.2f}%, {r_multiple:+.2f}R) - {exit_reason}"
                severity = "info" if pnl_dollars > 0 else "warning"

            notif_service._send_notification(
                subject=f"EXIT: {symbol}",
                message=message,
                kind="trade_exit",
                severity=severity,
                symbol=symbol,
                details={
                    "exit_price": final_exit_price,
                    "shares": shares_to_exit,
                    "pnl": f"{pnl_dollars:+.2f}" if not is_estimated_price else "PENDING",
                    "pnl_pct": pnl_pct if not is_estimated_price else None,
                    "r_multiple": r_multiple if not is_estimated_price else None,
                    "reason": exit_reason,
                    "trade_id": trade_id,
                    "is_estimated_price": is_estimated_price,
                },
            )
        except Exception as notif_e:
            logger.error(
                f"[EXIT_HANDLER] Failed to send exit notification for {symbol} trade {trade_id} "
                f"(non-blocking, exit already committed): {type(notif_e).__name__}: {notif_e}"
            )

        return {
            "success": True,
            "trade_id": trade_id,
            "shares_exited": shares_to_exit,
            # Cumulative across all legs when full_exit=True (matches what's stored in
            # algo_trades - see the multi-leg comment above); equal to this leg's own
            # pnl_dollars/pnl_pct/r_multiple for a partial exit or an as-yet-unreconciled
            # estimated fill, since there's no final trade-level total to report yet.
            "profit_loss_dollars": None if is_estimated_price else cumulative_pnl_dollars,
            "profit_loss_pct": None if is_estimated_price else cumulative_pnl_pct,
            "r_multiple": None if is_estimated_price else cumulative_r_multiple,
            "full_exit": full_exit,
            "is_estimated_price": is_estimated_price,
            "message": (
                f"Exited {shares_to_exit}sh of {symbol} @ ${final_exit_price:.2f} - "
                f"{'P&L PENDING fill reconciliation' if is_estimated_price else f'{cumulative_pnl_pct:+.2f}%, {cumulative_r_multiple:+.2f}R'}"
            ),
        }
