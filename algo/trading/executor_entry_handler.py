#!/usr/bin/env python3
"""Entry trade execution handler extracted from TradeExecutor.

Handles:
- Entry condition validation
- Order submission to Alpaca
- Trade record creation
- Position record creation
- TCA recording
- Entry notifications
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass
from datetime import date as _date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

import requests
from psycopg2.extensions import cursor as PsycopgCursor

from algo.config.credential_manager import get_algo_owner_cognito_sub
from algo.reporting import TradeNotificationService, notify
from algo.trading.exceptions import (
    DatabaseError,
    NotificationError,
    OrderExecutionError,
)
from algo.trading.handler_context import HandlerContext
from algo.trading.trade_context import TradeContext
from utils.trading import PositionStatus

logger = logging.getLogger(__name__)


@dataclass
class TradeInsertionRequest:
    """Value object encapsulating all parameters for trade record insertion."""

    trade_id: str
    idempotency_key: str
    symbol: str
    signal_date: _date | None
    entry_date: _date | None
    executed_price: Decimal | None
    shares: Decimal
    entry_reason: str
    stop_loss_price: Decimal
    stop_method: str | None
    target_1_price: Decimal | None
    target_2_price: Decimal | None
    target_3_price: Decimal | None
    order_status: str
    execution_mode: str
    alpaca_order_id: str
    position_size_pct: Decimal | None
    sqs: Any
    trend_score: float | None
    base_type: str | None
    base_quality: str | None
    stage_phase: str | None
    sector: str | None
    industry: str | None
    rs_percentile: float | None
    market_exposure_at_entry: float | None
    exposure_tier_at_entry: str | None
    stop_reasoning: str | None
    advanced_components: dict[str, Any] | None
    rejection_reason: str | None
    position_id: str | None = None  # FIXED: Link trade to position
    reentry_count: int = 0


# Map stage phase names to integer IDs for database storage
STAGE_PHASE_MAPPING = {
    "early": 1,
    "mid": 2,
    "late": 3,
}


def _redact_for_logs(message: str) -> str:
    """Redact sensitive trade data from log messages."""
    import re

    message = re.sub(r"\$[\d.]+", "$***", message)
    message = re.sub(r"(\d+)sh\b", "***sh", message)
    message = re.sub(r"([+-]\d+\.\d+)%", "***%", message)
    return message


class EntryHandler:
    """Handles entry trade execution logic."""

    def __init__(self, context: HandlerContext) -> None:
        self.context = context
        self.config = context.config
        self.validator = context.validator
        self.tca = context.tca
        self.t1_target_r_multiple = context.t1_target_r_multiple
        self.t2_target_r_multiple = context.t2_target_r_multiple
        self.t3_target_r_multiple = context.t3_target_r_multiple

    def _validate_stage_phase(self, stage_phase: str | None) -> int | None:
        """Validate stage_phase against known mapping.

        CRITICAL: When stage_phase is provided (not None), it MUST be valid.
        Fails fast if an invalid stage phase is provided-no silent defaults.

        Args:
            stage_phase: Stage phase name (early, mid, late) or None if not provided

        Returns:
            int: Integer ID from STAGE_PHASE_MAPPING if stage_phase provided and valid
            None: if stage_phase is None (optional field not provided)

        Raises:
            ValueError: If stage_phase is provided but not in STAGE_PHASE_MAPPING
        """
        if stage_phase is None:
            logger.debug("[ENTRY_HANDLER] Stage phase not provided (optional field, proceeding)")
            return None
        if stage_phase not in STAGE_PHASE_MAPPING:
            raise ValueError(
                f"[ENTRY_HANDLER] CRITICAL: Invalid stage_phase '{stage_phase}' provided. "
                f"Must be one of: {list(STAGE_PHASE_MAPPING.keys())}. "
                f"Cannot record trade with unknown stage phase-data integrity issue."
            )
        return STAGE_PHASE_MAPPING[stage_phase]

    def execute_entry(self, context: TradeContext) -> dict[str, Any]:  # noqa: C901
        """Execute entry trade through 4 phases: validate -> submit -> record -> notify.

        Returns: {
            'success': bool,
            'trade_id': str,
            'alpaca_order_id': str,
            'status': str,
            'message': str,
        }
        """
        logger.info(f"[ENTRY_HANDLER] execute_entry() called for {context.symbol}")
        entry_price = context.prices.entry_price
        shares = context.shares
        stop_loss_price = context.prices.stop_loss_price
        target_1_price = context.prices.target_1_price
        target_2_price = context.prices.target_2_price
        target_3_price = context.prices.target_3_price
        symbol = context.symbol
        signal_date = context.signal_date
        entry_date = context.entry_date

        if not symbol:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid",
                "message": "symbol is required",
            }

        valid, error_msg, validation_result = self.validator.validate_entry_preconditions(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            shares=shares,
            portfolio_value=self.context._get_portfolio_value(),
            signal_date=signal_date,
            entry_date=entry_date,
            target_1_price=target_1_price,
            target_2_price=target_2_price,
            target_3_price=target_3_price,
        )
        if not valid:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid",
                "message": error_msg,
            }

        # Apply auto-calculated targets if generated
        if "target_1_price" in validation_result:
            target_1_price = validation_result["target_1_price"]
        if "target_2_price" in validation_result:
            target_2_price = validation_result["target_2_price"]
        if "target_3_price" in validation_result:
            target_3_price = validation_result["target_3_price"]

        # Check for duplicate position via database
        def _check_dup_pos(cur: PsycopgCursor[Any]) -> dict[str, str] | None:
            is_dup, msg = self.validator.check_duplicate_position(cur, symbol, entry_date)
            if is_dup:
                return {"error": msg}
            logger.debug(f"[ENTRY_HANDLER] No duplicate position found for {symbol} on {entry_date}, can proceed")
            return None

        try:
            dup_result = self.context._with_cursor(_check_dup_pos)
            if dup_result and "error" in dup_result:
                return {
                    "success": False,
                    "trade_id": "",
                    "status": "duplicate_position",
                    "message": dup_result["error"],
                    "duplicate": True,
                }
        except DatabaseError as e:
            logger.error(f"Failed to check for duplicate position: {e}")
            raise

        # Normalize prices to 4 decimal places for consistent duplicate detection.
        # Phase 8 calculates prices as floats, which can have minor precision differences
        # on repeated runs (e.g., 197.8291 vs 197.8290). To ensure idempotent duplicate
        # detection works correctly, we round to match database precision BEFORE checking.
        entry_price = Decimal(str(entry_price)).quantize(Decimal("0.0001"), ROUND_HALF_UP)
        stop_loss_price = Decimal(str(stop_loss_price)).quantize(Decimal("0.0001"), ROUND_HALF_UP)

        # CRITICAL FIX: Initialize position_id BEFORE any database checks that might fail
        # Previously position_id was initialized after the idempotent duplicate check,
        # so if a DatabaseError occurred, position_id would be undefined when the exception
        # handler tried to use it, causing a NameError. Initializing here ensures it's
        # always defined for use in idempotency key and error handling.
        import uuid

        position_id = None

        # Check for idempotent duplicate (same symbol + signal_date = same signal, should not re-enter)
        def _check_idem_dup(cur: PsycopgCursor[Any]) -> dict[str, str] | None:
            is_dup, msg, existing_id = self.validator.check_idempotent_duplicate(
                cur, symbol, signal_date, entry_price, stop_loss_price
            )
            if is_dup:
                return {"error": msg, "existing_trade_id": existing_id}
            logger.debug(f"[ENTRY_HANDLER] No idempotent duplicate for {symbol} on {signal_date}")
            return None

        try:
            idem_result = self.context._with_cursor(_check_idem_dup)
            if idem_result and "error" in idem_result:
                return {
                    "success": False,
                    "trade_id": idem_result["existing_trade_id"],
                    "status": "duplicate_signal",
                    "message": idem_result["error"],
                    "duplicate": True,
                }
        except DatabaseError as e:
            logger.error(f"Failed to check for idempotent duplicate: {e}")
            raise

        # CRITICAL FIX: Check if an open position already exists for this symbol (from a prior entry in the same day).
        # Reuse it instead of creating duplicate positions. This prevents multiple positions per symbol.
        import hashlib

        from utils.db.context import DatabaseContext

        logger.info(f"[POSITION DEDUP] {symbol}: Checking for existing position created today (open or closed)...")
        try:
            with DatabaseContext("read") as read_cursor:
                read_cursor.execute(
                    """
                    SELECT position_id, status FROM algo_positions
                    WHERE symbol = %s
                    AND created_at::date = CURRENT_DATE
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                existing_pos = read_cursor.fetchone()
                if existing_pos:
                    position_id, existing_status = existing_pos
                    logger.info(
                        f"[POSITION REUSE] {symbol}: Reusing existing position {position_id} (status={existing_status})"
                    )
                else:
                    logger.debug(f"[POSITION DEDUP] {symbol}: No existing position found, will create new")
        except Exception as e:
            # BUG FOUND 2026-08-10 (position-sizing/entry boundary-condition audit): this used
            # to log and silently fall through, leaving `position_id` at its pre-check value
            # (None) - the exact same path taken when no existing position genuinely exists -
            # so a transient DB failure here was indistinguishable from "confirmed no
            # duplicate" and proceeded to generate a brand-new position_id below. Unlike the
            # two sibling duplicate checks immediately above (check_duplicate_position,
            # check_idempotent_duplicate - both correctly `raise` DatabaseError, letting
            # Phase 8's existing per-symbol exception handling block just this one entry), this
            # was the one fail-open exception in an otherwise fail-closed duplicate-detection
            # chain. algo_positions has no DB-level unique constraint on symbol (only on the
            # randomly-generated position_id, which can never collide) - this in-code check is
            # the ONLY thing preventing two separate open positions for the same symbol on the
            # same day if this exact entry gets processed twice (e.g. a retried orchestrator
            # run after a transient failure). Re-raise to match the sibling checks' fail-closed
            # behavior instead of silently risking a duplicate position.
            logger.error(f"[POSITION DEDUP ERROR] {symbol}: {type(e).__name__}: {e}", exc_info=True)
            raise

        # If no existing position found, generate new position_id
        if position_id is None:
            position_id = str(uuid.uuid4())
            logger.debug(f"[POSITION CREATE] {symbol}: Generated new position_id {position_id}")

        # Generate deterministic idempotency key for Alpaca order deduplication.
        # CRITICAL: Idempotency key MUST use ONLY stable values that don't change between retries.
        # Stable values:
        #   - symbol (immutable)
        #   - entry_price (from signal data, doesn't change)
        #   - signal_date (doesn't change)
        #
        # MUST NOT include position_id because:
        #   - position_id is randomly generated with uuid.uuid4() (line 284)
        #   - If trade insert fails and we retry, position_id changes
        #   - Different position_id → different idempotency_key
        #   - Different key → bypasses ON CONFLICT deduplication
        #   - Result: duplicate trades created (same issue as stop_loss_price bug Session 60)
        #
        # Load-bearing rule: feedback_idempotency_key_stop_loss_bug.md
        # "Idempotency key must use ONLY values that are deterministic across orchestrator reruns"

        # Normalize entry price to 4 decimals to ensure deterministic key across retries
        entry_price_normalized = f"{float(entry_price):.4f}"

        # Use only stable values that identify the SIGNAL, not the entry attempt:
        # symbol + entry_price + signal_date
        # This allows ON CONFLICT to properly deduplicate retries of the same signal
        key_source = f"{symbol}_{entry_price_normalized}_{signal_date}"
        idempotency_key = hashlib.sha256(key_source.encode()).hexdigest()

        # Execute entry in database transaction with locks
        def _execute_entry_txn(cur: PsycopgCursor[Any]) -> dict[str, Any]:
            """Execute entry transaction through 4 phases with database locks."""
            # Convert targets to Decimal for type safety
            tgt_1_price: Decimal | None = Decimal(str(target_1_price)) if target_1_price else None
            tgt_2_price: Decimal | None = Decimal(str(target_2_price)) if target_2_price else None
            tgt_3_price: Decimal | None = Decimal(str(target_3_price)) if target_3_price else None

            # PHASE 1: Validate
            is_valid, error_msg, error_details = self._validate_entry_phase(
                cur, symbol, signal_date, entry_price, stop_loss_price
            )
            if not is_valid:
                trade_id_for_error = None
                if error_details and "trade_id" in error_details:
                    trade_id_for_error = error_details["trade_id"]
                result: dict[str, Any] = {
                    "success": False,
                    "trade_id": trade_id_for_error,
                    "message": error_msg,
                }
                if error_details:
                    result.update({k: v for k, v in error_details.items() if k != "trade_id"})
                return result

            # See executor.py::_validate_entry_conditions for why this must come from
            # error_details rather than a hardcoded 0 - it's the actual computed value
            # max_reentries_per_name needs to ever fire past the first re-entry. On the
            # is_valid=True path _validate_entry_conditions always returns
            # {"reentry_count": ...} (never None, never missing the key) - fail loudly if
            # that contract is ever violated instead of silently defaulting to 0, which
            # would quietly neuter max_reentries_per_name exactly like the bug this
            # replaced.
            if error_details is None or "reentry_count" not in error_details:
                raise RuntimeError(
                    f"CRITICAL: _validate_entry_phase returned is_valid=True for {symbol} without "
                    f"'reentry_count' in error_details ({error_details!r}). This should be impossible - "
                    f"see executor.py::_validate_entry_conditions."
                )
            reentry_count = error_details["reentry_count"]

            # Generate trade ID and prepare for submission
            trade_id = f"TRD-{uuid.uuid4().hex[:10].upper()}"
            execution_mode = self.context.execution_mode

            # PHASE 2: Submit
            order_ok, order_error, order_status, alpaca_order_id, executed_price, rejection_reason, order_send_time = (
                self._submit_entry_phase(
                    cur,
                    symbol,
                    trade_id,
                    shares,
                    entry_price,
                    stop_loss_price,
                    tgt_1_price,
                    execution_mode,
                    idempotency_key,
                )
            )
            if not order_ok:
                # CRITICAL: this branch is the ONLY place order_ok can be False, and the ONLY
                # execution_mode that can ever reach it is "auto" - _submit_and_validate_order()
                # unconditionally returns success=True for paper/dry/review (they never touch
                # Alpaca; only "auto" sends a real order and can genuinely fail/be rejected). The
                # "in ('paper', 'auto')" check below therefore ALWAYS matched on every real live
                # order rejection, meaning a rejected/failed order in live trading silently
                # created a fake successful trade record (order_status="paper_pending",
                # executed_price=entry_price - a price nothing was ever actually filled at)
                # instead of halting - the "else: Live mode: Alpaca failure is a hard stop"
                # branch below was completely unreachable dead code for every valid
                # execution_mode value. Scoped to paper/dry modes: both are LOCAL-only and legitimately want to
                # keep tracking hypothetical trades for backtesting even without Alpaca
                # connectivity (they never touch real money either way); review/auto modes
                # must now correctly fall through to the hard-stop branch.
                if execution_mode in ("paper", "dry"):
                    logger.warning(
                        f"[PAPER MODE] {symbol}: Alpaca order failed ({order_error}), "
                        f"but creating trade record in paper mode for backtest/tracking"
                    )
                    # Use entry price as executed price since Alpaca didn't fill the order
                    executed_price = entry_price
                    order_status = "paper_pending"
                    alpaca_order_id = ""
                    rejection_reason = f"Paper mode - Alpaca unavailable: {order_error[:200]}"
                    # Continue to Phase 3 to record the trade
                else:
                    # Live/auto mode: Alpaca order failure or rejection is a hard stop - do NOT
                    # fabricate a trade record for a position that was never actually opened.
                    logger.critical(
                        f"[ENTRY_HANDLER CRITICAL] {symbol}: Order failed/rejected in "
                        f"execution_mode={execution_mode!r} - NOT creating a trade record. "
                        f"Reason: {order_error}"
                    )
                    return {
                        "success": False,
                        "trade_id": trade_id,
                        "status": "failed",
                        "message": order_error,
                    }

            # Handle slippage: recalculate targets if fill price differs from signal
            if executed_price is None:
                raise ValueError(
                    f"[ENTRY_HANDLER CRITICAL] {symbol}: Order executed but executed_price not captured. "
                    f"Cannot record position without actual fill price for accurate cost basis."
                )
            if executed_price != entry_price:
                ep = float(executed_price)
                ep_price = float(entry_price)
                slippage_pct = float(abs((ep - ep_price) / ep_price * 100))
                if slippage_pct > 5.0:
                    logger.warning(
                        f"[SLIPPAGE ALERT] {symbol}: excessive slippage {slippage_pct:.2f}% "
                        f"(signal=${entry_price:.2f}, fill=${executed_price:.2f}). "
                        "Verify market conditions. Order may need review."
                    )
                tgt_1_price, tgt_2_price, tgt_3_price = self._recalculate_targets_for_slippage(
                    executed_price, entry_price, stop_loss_price
                )

            # PHASE 3: Record
            final_order_status = self._record_entry_phase(
                cur,
                trade_id,
                symbol,
                shares,
                entry_price,
                executed_price,
                stop_loss_price,
                tgt_1_price,
                tgt_2_price,
                tgt_3_price,
                order_status,
                alpaca_order_id,
                context,
                rejection_reason,
                idempotency_key,
                order_send_time,
                reentry_count,
                position_id,
            )

            if final_order_status in ("invalid", "unknown"):
                return {
                    "success": False,
                    "trade_id": trade_id,
                    "status": final_order_status,
                    "message": f"Order status changed to {final_order_status}",
                }

            # PHASE 4: Notify
            self._notify_entry_phase(
                symbol,
                shares,
                executed_price,
                stop_loss_price,
                tgt_1_price,
                context.signals.base_type,
                trade_id,
            )

            return {
                "success": True,
                "trade_id": trade_id,
                "alpaca_order_id": alpaca_order_id,
                "status": final_order_status,
                "message": f"{shares} sh {symbol} @ ${executed_price:.2f}",
            }

        # Execute entry transaction with locks
        try:
            return cast(dict[str, Any], self.context._with_cursor(_execute_entry_txn, acquire_locks=True))
        except Exception as e:
            logger.exception(f"Entry execution failed: {e}")
            raise

    def _recalculate_targets_for_slippage(
        self, executed_price: Decimal, entry_price: Decimal, stop_loss_price: Decimal
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Recalculate targets based on actual fill price due to slippage."""
        executed_price_dec = Decimal(str(executed_price))
        entry_price_dec = Decimal(str(entry_price))
        slippage_pct = float(
            ((executed_price_dec - entry_price_dec) / entry_price_dec * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        logger.info(_redact_for_logs(f"Slippage: {slippage_pct:+.2f}%"))

        stop_price_dec = Decimal(str(stop_loss_price))
        actual_risk_per_share = executed_price_dec - stop_price_dec
        if actual_risk_per_share > 0:
            t1_r = Decimal(str(self.t1_target_r_multiple))
            t2_r = Decimal(str(self.t2_target_r_multiple))
            t3_r = Decimal(str(self.t3_target_r_multiple))

            target_1 = (executed_price_dec + (actual_risk_per_share * t1_r)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            target_2 = (executed_price_dec + (actual_risk_per_share * t2_r)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            target_3 = (executed_price_dec + (actual_risk_per_share * t3_r)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            return target_1, target_2, target_3

        return (
            Decimal(str(entry_price)).quantize(Decimal("0.01")),
            Decimal(str(entry_price)).quantize(Decimal("0.01")),
            Decimal(str(entry_price)).quantize(Decimal("0.01")),
        )

    def _calculate_position_size_pct(
        self, shares: Decimal, price: Decimal, portfolio_value: Decimal | None
    ) -> Decimal | None:
        """Calculate position size as percentage of portfolio.

        Raises ValueError if portfolio value is missing or invalid.
        Cannot proceed without knowing portfolio size for position sizing.
        """
        if portfolio_value is None:
            raise ValueError(
                "CRITICAL: Portfolio value is None. Cannot calculate position size percentage. "
                "Alpaca API must return valid account equity or portfolio snapshot must be fresh."
            )
        if portfolio_value <= 0:
            raise ValueError(
                f"CRITICAL: Portfolio value is {portfolio_value}. "
                "Cannot calculate position size with zero or negative portfolio. "
                "Account may be liquidated or in error state."
            )

        # CRITICAL FIX: Convert all operands to Decimal with string conversion
        # to avoid Decimal * float type errors (feedback_psycopg2_decimal_arithmetic)
        shares_dec = Decimal(str(shares)) if not isinstance(shares, Decimal) else shares
        price_dec = Decimal(str(price)) if not isinstance(price, Decimal) else price
        pv_dec = Decimal(str(portfolio_value)) if not isinstance(portfolio_value, Decimal) else portfolio_value

        position_size = (shares_dec * price_dec / pv_dec * Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return position_size

    def _build_entry_reason(
        self,
        base_type: str | None,
        stage_phase: str | None,
        exposure_tier: str | None,
    ) -> str:
        """Build comprehensive entry reason string."""
        parts = ["Algo signal - all tiers passed"]
        if base_type:
            parts.append(f"base={base_type}")
        if stage_phase:
            parts.append(f"phase={stage_phase}")
        if exposure_tier:
            parts.append(f"exposure={exposure_tier}")
        return " | ".join(parts)

    def _insert_trade_record(
        self,
        cur: PsycopgCursor[Any],
        request: TradeInsertionRequest,
    ) -> None:
        """Insert trade record into database with idempotency_key for request-level deduplication.

        Idempotency: If the same idempotency_key is submitted twice, the second attempt
        succeeds without error (ON CONFLICT DO UPDATE ensures this is a no-op update).
        This is critical because Phase 8 can run multiple times on the same signal date,
        and generating the same idempotency_key is correct behavior (prevents duplicate
        real orders at the broker). The database insert must also be idempotent.
        """
        try:
            logger.debug(
                f"[TRADE INSERT] {request.symbol}: trade_id={request.trade_id}, "
                f"signal_date={request.signal_date}, entry_date={request.entry_date}, "
                f"entry_price={request.executed_price}, qty={request.shares}, "
                f"stop={request.stop_loss_price}"
            )
            cur.execute(
                """
                INSERT INTO algo_trades (
                    trade_id, symbol, signal_date, entry_date, trade_date, entry_price, entry_time, entry_quantity, entry_reason,
                    stop_loss_price, target_1_price, target_2_price, target_3_price,
                    signal_quality_score, trend_template_score, base_type, base_quality, stage_phase,
                    rs_percentile, market_exposure_at_entry, exposure_tier_at_entry, stop_reasoning, advanced_components,
                    status, sector, industry, execution_mode, idempotency_key, position_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (idempotency_key) DO UPDATE SET
                    entry_price = EXCLUDED.entry_price,
                    entry_time = EXCLUDED.entry_time,
                    entry_quantity = EXCLUDED.entry_quantity,
                    signal_date = EXCLUDED.signal_date,
                    trade_date = EXCLUDED.trade_date,
                    signal_quality_score = EXCLUDED.signal_quality_score,
                    trend_template_score = EXCLUDED.trend_template_score,
                    position_id = EXCLUDED.position_id,
                    execution_mode = EXCLUDED.execution_mode,
                    status = EXCLUDED.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    request.trade_id,
                    request.symbol,
                    request.signal_date,
                    request.entry_date,
                    request.entry_date,  # duplicate for both entry_date and trade_date columns
                    request.executed_price,
                    request.shares,
                    request.entry_reason,
                    request.stop_loss_price,
                    request.target_1_price,
                    request.target_2_price,
                    request.target_3_price,
                    request.sqs,
                    request.trend_score,
                    request.base_type,
                    request.base_quality,
                    request.stage_phase,
                    request.rs_percentile,
                    request.market_exposure_at_entry,
                    request.exposure_tier_at_entry,
                    request.stop_reasoning,
                    request.advanced_components,
                    request.order_status,
                    request.sector,
                    request.industry,
                    request.execution_mode,
                    request.idempotency_key,
                    request.position_id,
                ),
            )
            logger.info(
                f"[TRADE INSERT] {request.symbol}: SUCCEEDED with trade_id={request.trade_id} status={request.order_status} position_id={request.position_id}"
            )

            # CRITICAL VALIDATION: Verify that open trades NEVER have exit_price set
            # If exit_price is set for an open trade, it indicates a bug in entry logic or data corruption
            cur.execute("SELECT exit_price FROM algo_trades WHERE trade_id = %s", (request.trade_id,))
            verify_row = cur.fetchone()
            if (
                verify_row
                and verify_row[0] is not None
                and request.order_status in ("open", "paper_pending", "pending", "filled", "partially_filled")
            ):
                logger.critical(
                    f"[TRADE INSERT VALIDATION CRITICAL] {request.symbol}: Trade {request.trade_id} has "
                    f"status='{request.order_status}' but exit_price={verify_row[0]} (should be NULL for open trades). "
                    f"This indicates a data corruption bug - exit_price must NEVER be set for open trades!"
                )
                raise ValueError(
                    f"[CRITICAL BUG] Trade inserted with status='open' but exit_price is set to {verify_row[0]}. "
                    f"Open trades must have exit_price=NULL. This is a data integrity violation."
                )
        except Exception as e:
            logger.critical(
                f"[TRADE INSERT FAILED] {request.symbol}: trade_id={request.trade_id}, "
                f"error={type(e).__name__}: {str(e)[:500]}"
            )
            raise

    def _record_tca(
        self,
        trade_id: str,
        symbol: str,
        entry_price: Decimal,
        executed_price: Decimal | None,
        order_status: str,
        shares_requested: Decimal,
        shares_filled: Decimal,
        order_send_time: float | None,
    ) -> None:
        """Record trade cost analysis (execution quality). Best-effort - must never fail
        the entry.

        CRITICAL FIX: this method (via _record_entry_phase) runs inside the same
        _execute_entry_txn transaction as the algo_trades/algo_positions INSERT, and is
        only called when execution_mode == "auto" after the order has already filled at
        the broker (see call site: `if ... execution_mode == "auto" and order_status in
        ("filled", "partially_filled")`) - an irreversible, already-happened event. The
        old `except DatabaseError` could never match anything this body actually raises:
        self.tca.record_fill() raises bare psycopg2 errors, RuntimeError, or
        ValueError/TypeError/ZeroDivisionError - never algo.trading.exceptions.
        DatabaseError - so every real failure mode (including the two explicit
        ValueErrors below for missing/negative timing, and a failed TCA slippage alert)
        propagated uncaught out of this function, out of _execute_entry_txn, out of
        _with_cursor's DatabaseContext("write") block, which rolls back on any
        exception - deleting the already-inserted trade/position rows for a position
        already bought for real at the broker. Same bug class as
        ExitHandler._execute_exit's notification block and _send_entry_notification
        (see their fix comments) - TCA (execution-quality/compliance metadata) is not
        critical to position tracking and must never revert a trade that already
        happened.
        """
        try:
            # CRITICAL FIX: order_send_time used to be read as self.context._order_send_time -
            # self.context is a HandlerContext instance, but _order_send_time was only ever set
            # on the TradeExecutor instance (inside _submit_and_validate_order, a bound method
            # callback that keeps its original `self` regardless of how HandlerContext invokes
            # it). That read always raised AttributeError in execution_mode="auto" - see
            # _submit_and_validate_order's docstring in executor.py for the full live-reproduced
            # failure. Now passed explicitly from the caller instead of relying on shared state.
            if order_send_time is None:
                raise ValueError(f"[TCA] {symbol}: order_send_time not provided for auto-mode fill")
            execution_latency_ms = int((time.time() - order_send_time) * 1000)
            if execution_latency_ms < 0:
                raise ValueError(f"[TCA] {symbol}: negative latency {execution_latency_ms}ms")

            # shares_requested/shares_filled were previously hardcoded to 1/1, which made
            # fill_rate_pct (algo/trading/tca.py::record_fill, shares_filled/shares_requested*100)
            # always report 100% - a partial fill (e.g. 60 of 100 shares) was recorded in the
            # TCA execution-quality audit trail identically to a full fill, masking the exact
            # condition TCA exists to catch.
            tca_result = self.tca.record_fill(
                trade_id=trade_id,
                symbol=symbol,
                signal_price=entry_price,
                fill_price=(executed_price if executed_price else entry_price),
                shares_requested=int(shares_requested),
                shares_filled=int(shares_filled),
                side="BUY",
                execution_latency_ms=execution_latency_ms,
            )

            # Alert if slippage excessive
            if "alert" in tca_result:
                try:
                    alert_data = tca_result["alert"]
                    # strict=True: without it, notify() never raises NotificationError at
                    # all, making the except clause below dead code - see notify()'s docstring.
                    notify(
                        alert_data["severity"].lower(),
                        title=f"TCA Alert: {alert_data['severity']}",
                        message=alert_data["message"],
                        strict=True,
                    )
                except NotificationError as e:
                    logger.error(
                        f"[TCA] Failed to send TCA slippage alert for {symbol} trade {trade_id} (non-blocking): {e}"
                    )
        except Exception as e:
            logger.error(
                f"[TCA] Failed to record execution-quality data for {symbol} trade {trade_id} "
                f"(non-blocking, trade already committed): {type(e).__name__}: {e}"
            )

    def _validate_entry_phase(
        self,
        cur: PsycopgCursor[Any],
        symbol: str,
        signal_date: _date | None,
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> tuple[bool, str, dict[str, Any]]:
        """PHASE 1: Validate entry conditions within transaction.

        CRITICAL: Reject positions without valid downside protection.
        """
        # Validate stop loss exists and is properly configured (fail-fast on missing protection)
        if stop_loss_price is None:
            return False, f"{symbol}: Cannot enter position without stop_loss_price (required for risk management)", {}

        stop_dec = Decimal(str(stop_loss_price))
        entry_dec = Decimal(str(entry_price))

        if stop_dec <= 0:
            return False, f"{symbol}: Stop loss must be > 0, got {stop_dec}. Zero stop = immediate liquidation.", {}

        if stop_dec >= entry_dec:
            return False, f"{symbol}: Stop loss {stop_dec} must be < entry price {entry_dec}", {}

        is_valid, error_msg, error_details = self.context._validate_entry_conditions(
            cur, symbol, signal_date, entry_price, stop_loss_price
        )
        return is_valid, error_msg, error_details if error_details else {}

    def _submit_entry_phase(
        self,
        cur: PsycopgCursor[Any],
        symbol: str,
        trade_id: str,
        shares: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        target_1_price: Decimal | None,
        execution_mode: str,
        idempotency_key: str,
    ) -> tuple[bool, str, str, str, Decimal | None, str | None, float | None]:
        """PHASE 2: Submit order and validate result.

        Returns the same 6 fields as before plus order_send_time (None for paper/dry/review,
        which never actually send to a broker) so the caller can pass it through to TCA latency
        recording without either side needing to share hidden state via self.context.
        """
        # CRITICAL FIX: was captured inside TradeExecutor._submit_and_validate_order as
        # self._order_send_time, then read back here as self.context._order_send_time -
        # self.context is a different object (HandlerContext) than the TradeExecutor instance
        # the bound-method callback actually sets attributes on, so that read always raised
        # AttributeError in execution_mode="auto" (see _submit_and_validate_order's docstring
        # for the full live-reproduced failure). Capturing it locally here and threading it
        # through the return value removes the cross-object dependency entirely.
        order_send_time = time.time()
        order_ok, alpaca_order_id, order_status, order_error, executed_price, rejection_reason, order_result = (
            self.context._submit_and_validate_order(
                symbol,
                trade_id,
                shares,
                entry_price,
                stop_loss_price,
                target_1_price,
                execution_mode,
                idempotency_key,
            )
        )

        if not order_ok:
            return False, order_error, "", "", None, rejection_reason, order_send_time

        # Verify bracket orders in auto mode
        if execution_mode == "auto":
            if order_result is None:
                return (
                    False,
                    "Order result missing - bracket validation failed",
                    "",
                    "",
                    None,
                    rejection_reason,
                    order_send_time,
                )
            legs = order_result.get("legs")
            if legs is None:
                raise RuntimeError(
                    f"[ENTRY_HANDLER] {symbol}: OrderManager returned success=True but no 'legs' field. "
                    f"Cannot validate bracket order without legs. OrderManager contract violated."
                )

            order_class = order_result.get("order_class")
            if order_class is None:
                raise RuntimeError(
                    f"[ENTRY_HANDLER] {symbol}: OrderManager result missing 'order_class' field. "
                    f"Cannot validate order type. OrderManager contract violated."
                )

            if order_class == "bracket":
                if len(legs) < 2:
                    try:
                        self.context._cancel_bracket_orders(alpaca_order_id)
                    except (
                        OrderExecutionError,
                        DatabaseError,
                        requests.RequestException,
                        requests.Timeout,
                    ) as e:
                        logger.warning(f"Failed to cancel bracket order {alpaca_order_id}: {e}")
                    return (
                        False,
                        f"Bracket order missing stop loss leg ({len(legs)} legs)",
                        "",
                        "",
                        None,
                        rejection_reason,
                        order_send_time,
                    )

                has_stop_loss = any(leg.get("order_type") == "stop" for leg in legs if isinstance(leg, dict))
                has_take_profit = any(leg.get("order_type") == "limit" for leg in legs if isinstance(leg, dict))

                if not has_stop_loss or not has_take_profit:
                    try:
                        self.context._cancel_bracket_orders(alpaca_order_id)
                    except (
                        OrderExecutionError,
                        DatabaseError,
                        requests.RequestException,
                        requests.Timeout,
                    ) as e:
                        logger.warning(f"Failed to cancel incomplete bracket order {alpaca_order_id}: {e}")
                    missing = []
                    if not has_stop_loss:
                        missing.append("stop_loss")
                    if not has_take_profit:
                        missing.append("take_profit")
                    return (
                        False,
                        f"Bracket order missing required legs: {', '.join(missing)}",
                        "",
                        "",
                        None,
                        rejection_reason,
                        order_send_time,
                    )

            # CRITICAL FIX: Wait for order to actually fill before writing to DB
            # Do NOT trust the order submission response alone - verify fill with broker
            logger.info(f"[ENTRY_HANDLER] {symbol} {alpaca_order_id}: Waiting for order fill confirmation...")
            fill_ok, confirmed_fill_price, fill_error = self.context._wait_for_order_fill(
                symbol, alpaca_order_id, max_wait_seconds=30
            )
            if not fill_ok:
                # Order did not fill - do NOT write to DB
                #
                # BUG FOUND 2026-08-11: the "Check for order rejection/cancellation" block that
                # used to follow this one (removed here) checked `order_status`, which is set
                # once from _submit_and_validate_order's IMMEDIATE POST response (above, before
                # the fill-wait) and never reassigned - by construction it can only be
                # "new"/"accepted"/"pending_new" at this point (anything Alpaca rejects outright
                # at POST time already returns order_ok=False and never reaches here). So
                # `order_status in ("rejected", "cancelled", "expired")` was structurally
                # unreachable dead code: this `if not fill_ok:` branch is the ONLY path that
                # actually observes a mid-wait rejection/cancellation/expiry (via
                # wait_for_order_fill's own status polling), and it only logged
                # logger.critical() - never called the GOVERNANCE-mandated notify() alert the
                # dead code below it was supposed to send. A real live order rejected/cancelled/
                # expired during the up-to-30s fill-wait window (a real scenario - e.g. Alpaca
                # accepts then later rejects for insufficient buying power) reached the operator
                # only as a log line, never an actual alert. Moved the notify() call here, the
                # one path that's actually reachable.
                logger.critical(
                    f"[ENTRY_HANDLER CRITICAL] {symbol} {alpaca_order_id}: Order failed to fill: {fill_error}. "
                    f"Will NOT create trade record (position does not exist at broker)."
                )
                try:
                    # strict=True: without it, notify() never raises NotificationError at
                    # all, making the except clause below dead code - see notify()'s docstring.
                    notify(
                        "critical",
                        title=f"Order fill failed: {symbol}",
                        message=f"Trade {trade_id}: {shares}sh @ ${entry_price:.2f} - {fill_error}",
                        strict=True,
                    )
                except NotificationError as e:
                    raise RuntimeError(
                        f"CRITICAL: Failed to send fill-failure alert for {symbol} ({fill_error}): {e}. "
                        f"Trader was NOT notified that the order failed to fill."
                    ) from e
                try:
                    self.context._cancel_bracket_orders(alpaca_order_id)
                except (
                    OrderExecutionError,
                    DatabaseError,
                    requests.RequestException,
                    requests.Timeout,
                ) as e:
                    logger.warning(f"Failed to cancel failed order {alpaca_order_id}: {e}")
                return (False, fill_error, "", "", None, None, order_send_time)

            # Order filled - use actual fill price from broker
            if confirmed_fill_price is not None:
                executed_price = Decimal(str(confirmed_fill_price))
                logger.info(f"[ENTRY_HANDLER] {symbol}: Order confirmed filled @ ${executed_price}")

        return True, "", order_status, alpaca_order_id, executed_price, rejection_reason, order_send_time

    def _record_entry_phase(
        self,
        cur: PsycopgCursor[Any],
        trade_id: str,
        symbol: str,
        shares: Decimal,
        entry_price: Decimal,
        executed_price: Decimal | None,
        stop_loss_price: Decimal,
        target_1_price: Decimal | None,
        target_2_price: Decimal | None,
        target_3_price: Decimal | None,
        order_status: str,
        alpaca_order_id: str,
        context: TradeContext,
        rejection_reason: str | None,
        idempotency_key: str,
        order_send_time: float | None,
        reentry_count: int = 0,
        position_id: str | None = None,
    ) -> str:
        """PHASE 3: Insert trade record, position record, record TCA."""
        # Generate position_id if not provided (required for linking trade to position)
        # CRITICAL FIX: Ensure position_id is assigned BEFORE any use in this function
        # to avoid Python's local variable scoping issue where assignment anywhere
        # in the function makes it local throughout, causing "not defined" errors.
        if position_id is None:
            position_id = str(uuid.uuid4())
        if executed_price is None:
            raise ValueError(
                f"[ENTRY_HANDLER CRITICAL] {symbol}: Recording entry without executed_price. "
                f"Cannot calculate position size percentage or record accurate cost basis."
            )

        # Resolve the FINAL order_status and actual filled share count BEFORE building the
        # trade record, so algo_trades and algo_positions can never disagree. Previously this
        # verification/correction ran AFTER _insert_trade_record() below, which had two
        # consequences: (1) a partial fill (e.g. 100 shares requested, 60 filled) wrote
        # algo_trades.quantity/entry_quantity = 100 (the request) while algo_positions.quantity
        # = 60 (the actual fill) - the trade ledger permanently overstated the position by the
        # unfilled portion, and everything downstream that reads algo_trades quantities
        # (reconciliation, performance reporting) inherited the drift; (2) in execution_mode
        # "auto", if Alpaca's verified status disagreed with the caller's optimistic
        # order_status (e.g. the order was actually canceled after being optimistically passed
        # in as "filled"), the trade record was already committed with the wrong status before
        # verification ran.
        actual_shares = shares
        if self.context.execution_mode == "auto" and alpaca_order_id:
            verified_status = self.context._verify_order_status(alpaca_order_id)
            if verified_status is None:
                raise OrderExecutionError(
                    f"Order {alpaca_order_id}: verification failed (status is None). "
                    f"Cannot record position without verified fill status. "
                    f"This indicates Alpaca API communication error or order data corruption."
                )
            order_status = str(verified_status)

        if order_status == "partially_filled" and alpaca_order_id:
            filled_qty = self.context._get_order_filled_quantity(alpaca_order_id)
            if filled_qty is not None and filled_qty > 0:
                # CRITICAL FIX: Convert filled_qty from float to Decimal
                # filled_qty comes from Alpaca API as float, but TradeInsertionRequest expects Decimal
                # Without conversion, Decimal arithmetic later raises TypeError: unsupported operand types
                actual_shares = Decimal(str(filled_qty))
                logger.info(_redact_for_logs(f"Partial fill: {actual_shares} of {shares} shares"))

        # Calculate position size percentage
        pv_for_pct = self.context._get_portfolio_value()
        position_size_pct = self._calculate_position_size_pct(actual_shares, executed_price, pv_for_pct)

        entry_reason = self._build_entry_reason(
            context.signals.base_type,
            context.signals.stage_phase,
            context.market.exposure_tier_at_entry,
        )

        # CRITICAL FIX (Session 379): Validate sqs is being passed through TradeContext
        # This ensures signal_quality_score is stored in database for all trades
        # GOVERNANCE: Finance apps cannot accept NULL signal_quality_score for any trade
        if context.sqs is None:
            raise ValueError(
                f"[ENTRY_HANDLER CRITICAL] {symbol}: signal_quality_score is None in TradeContext. "
                f"Cannot proceed with trade entry - signal quality validation is mandatory. "
                f"This indicates upstream Phase 7 signal quality score computation failed or did not complete. "
                f"Check: (1) Phase 7 signal quality score computation status, "
                f"(2) buy_sell_daily table has signal_quality_score populated for this signal, "
                f"(3) SignalQualityScoresLoader executed without errors. "
                f"Trades without valid signal quality scores must not be entered."
            )
        logger.debug(f"[ENTRY_HANDLER] {symbol}: sqs={context.sqs} type={type(context.sqs).__name__}")

        trade_request = TradeInsertionRequest(
            trade_id=trade_id,
            idempotency_key=idempotency_key,
            symbol=symbol,
            signal_date=context.signal_date,
            entry_date=context.entry_date,
            executed_price=executed_price,
            shares=actual_shares,
            entry_reason=entry_reason,
            stop_loss_price=stop_loss_price,
            stop_method=context.execution.stop_method,
            target_1_price=target_1_price,
            target_2_price=target_2_price,
            target_3_price=target_3_price,
            order_status=order_status,
            execution_mode=self.context.execution_mode,
            alpaca_order_id=alpaca_order_id,
            position_size_pct=position_size_pct,
            sqs=context.sqs,
            trend_score=context.signals.trend_score,
            base_type=context.signals.base_type,
            base_quality=context.signals.base_quality,
            stage_phase=context.signals.stage_phase,
            sector=context.market.sector,
            industry=context.market.industry,
            rs_percentile=context.signals.rs_percentile,
            market_exposure_at_entry=context.market.market_exposure_at_entry,
            exposure_tier_at_entry=context.market.exposure_tier_at_entry,
            stop_reasoning=context.execution.stop_reasoning,
            advanced_components=context.signals.advanced_components,
            rejection_reason=rejection_reason,
            reentry_count=reentry_count,
            # Only link to a position when one will actually be created below (order_status
            # in filled/partially_filled/paper_pending/open - "open" is the immediate
            # simulated-fill status used by paper/dry execution_mode). The FK is DEFERRABLE
            # INITIALLY DEFERRED so the position row (inserted after this trade row, same
            # transaction) satisfies it by commit time, but a trade whose order didn't fill
            # (e.g. "pending" in review mode) has no corresponding position ever, so
            # position_id must stay NULL for those.
            position_id=(
                position_id if order_status in ("filled", "partially_filled", "paper_pending", "open") else None
            ),
        )
        # CRITICAL DEBUG: Log what we're about to insert before persisting
        # This helps diagnose why signal fields end up as NULL in the database
        logger.info(
            f"[TRADE INSERT DEBUG] {trade_request.symbol}: "
            f"sqs={trade_request.sqs} trend={trade_request.trend_score} "
            f"base_type={trade_request.base_type} base_quality={trade_request.base_quality}"
        )

        logger.debug(f"[TRADE INSERT] About to insert trade {trade_request.trade_id} for {symbol}")
        self._insert_trade_record(cur, trade_request)
        logger.debug(f"[TRADE INSERT] Successfully inserted trade {trade_request.trade_id} for {symbol}")

        # Insert position record if order was filled or paper_pending (paper mode tracking)
        # PAPER MODE: Create positions for paper_pending trades to maintain portfolio state
        # Live mode: Only create positions for actual filled/partially_filled orders
        if order_status in ("filled", "partially_filled", "paper_pending", "open"):
            # CRITICAL FIX: Use the position_id that was set at line 873 and linked to the trade.
            # Do NOT regenerate it here - trade_request.position_id may be None if order_status
            # didn't match the condition at line 969, but the position_id variable from line 873
            # is what was actually used to create the trade record. Regenerating here creates
            # a position with a DIFFERENT ID than the trade, breaking the foreign key relationship.
            # This was causing closed positions with orphaned trade_ids_arr.
            # Use the position_id that was already generated and linked to the trade at line 873.
            entry_date = context.entry_date

            # order_status/actual_shares were already verified/corrected above, before the
            # trade record was inserted, so both algo_trades and algo_positions use the same
            # final values here.

            # Validate position value
            position_value = Decimal(str(actual_shares)) * Decimal(str(executed_price))
            if position_value <= 0:
                return "invalid"

            # CRITICAL VALIDATION: entry_price, entry_date, AND stop_loss must NEVER be NULL
            # Session 281 audit found NULL stop_loss causes exit failures
            if executed_price is None or entry_date is None:
                raise ValueError(
                    f"[POSITION_CREATION CRITICAL] {symbol}: Cannot create position with NULL entry_price or entry_date. "
                    f"executed_price={executed_price}, entry_date={entry_date}. "
                    f"Portfolio reconciliation depends on having entry prices for all positions."
                )
            # CRITICAL: Stop price must be set before position creation
            # Null stop price blocks all stop-based exit strategies (stop-raise, stop-loss)
            # BUG FOUND 2026-08-10 (via systematic sweep for the NaN-comparison-guard bug
            # class - after fuzzing found it 8 other times this session): `stop_loss_price
            # <= 0` doesn't catch NaN (NaN comparisons are always False in Python). This
            # guard runs AFTER the order has already executed/filled - a NaN here would
            # write stop_loss_price=NaN into algo_positions for a real, already-open
            # position instead of being rejected, corrupting every downstream risk
            # calculation, position sizing check, and exit decision for that position.
            if (
                stop_loss_price is None
                or (isinstance(stop_loss_price, float) and (math.isnan(stop_loss_price) or math.isinf(stop_loss_price)))
                or stop_loss_price <= 0
            ):
                raise ValueError(
                    f"[POSITION_CREATION CRITICAL] {symbol}: Cannot create position with NULL or invalid stop_loss. "
                    f"Stop loss must be > 0 and < entry price. Got: {stop_loss_price}. "
                    f"Check Phase 8 entry validation - stop price calculation must complete before position insert."
                )

            # Use the position_id that was created when inserting the trade
            # This ensures trade and position are linked via foreign key
            # CRITICAL: Paper_pending trades MUST create open positions for portfolio tracking
            # This ensures paper mode trading maintains accurate position state
            #
            # CRITICAL FIX: this previously used the literal string "paper_open" - a value
            # that isn't in the PositionStatus enum at all and that almost every real
            # position query in this codebase (exit_engine.py's core exit-candidate query,
            # circuit_breaker.py's _check_total_risk/_check_win_rate_floor/
            # _check_sector_drawdown/_check_sector_concentration, position_monitor.py) checks
            # against PositionStatus.OPEN.value ("open") specifically, not "paper_open". A
            # position created via this paper-mode-Alpaca-unavailable fallback path (see
            # order_status="paper_pending" above) would therefore be invisible to every
            # automated stop-loss/target exit check and every risk-limit halt check - the
            # exact same "no bypasses" bug class as this session's other TradeStatus.all_open()
            # fixes, just on the PositionStatus side and with an undeclared status string
            # instead of an incomplete-but-declared one. algo/infrastructure/reconciliation.py
            # separately handles "paper_open" via `status IN ('open', 'paper_open')` in a few
            # aggregate-count queries, but treats it identically to "open" there too - there
            # was never a reason for these to be different values. Use PositionStatus.OPEN.value
            # for both cases so every existing "status = 'open'" check already covers it.
            # CRITICAL FIX: this previously used the literal string "paper_open" - a value
            # that isn't in the PositionStatus enum at all and that almost every real
            # position query in this codebase (exit_engine.py's core exit-candidate query,
            # circuit_breaker.py's _check_total_risk/_check_win_rate_floor/
            # _check_sector_drawdown/_check_sector_concentration, position_monitor.py) checks
            # against PositionStatus.OPEN.value ("open") specifically, not "paper_open". A
            # position created via this paper-mode-Alpaca-unavailable fallback path (see
            # order_status="paper_pending" above) would therefore be invisible to every
            # automated stop-loss/target exit check and every risk-limit halt check - the
            # exact same "no bypasses" bug class as this session's other TradeStatus.all_open()
            # fixes, just on the PositionStatus side and with an undeclared status string
            # instead of an incomplete-but-declared one. algo/infrastructure/reconciliation.py
            # separately handles "paper_open" via `status IN ('open', 'paper_open')` in a few
            # aggregate-count queries, but treats it identically to "open" there too - there
            # was never a reason for these to be different values. Use PositionStatus.OPEN.value
            # for both cases so every existing "status = 'open'" check already covers it.
            position_status = PositionStatus.OPEN.value

            # r_multiple at the instant of entry is 0 (current_price == executed_price, no
            # movement yet), not the 1.0 this previously hardcoded - position_monitor.py's
            # _persist_review recomputes this live on every subsequent cycle against
            # stop_loss_price, so this initial value only shows until the first review runs.
            r_multiple = None
            if stop_loss_price and executed_price:
                risk_per_share = executed_price - stop_loss_price
                if risk_per_share > 0:
                    r_multiple = 0.0

            # CRITICAL FIX: Calculate and persist position-level risk_pct
            # This is the percentage risk of the trade based on stop loss distance
            # Formula: (entry_price - stop_loss) / entry_price * 100
            # This field is REQUIRED by circuit_breaker.py for portfolio risk calculation
            risk_pct = None
            if executed_price and stop_loss_price and executed_price > 0:
                # Convert Decimals to float before arithmetic to avoid mixed-type operations
                ep = float(executed_price)
                sl = float(stop_loss_price)
                risk_pct = float(((ep - sl) / ep) * 100.0)

            self._upsert_position_record(
                cur=cur,
                position_id=position_id,
                symbol=symbol,
                trade_id=trade_id,
                actual_shares=actual_shares,
                executed_price=executed_price,
                position_value=position_value,
                position_status=position_status,
                entry_date=entry_date,
                stop_loss_price=stop_loss_price,
                target_1_price=target_1_price,
                target_2_price=target_2_price,
                target_3_price=target_3_price,
                r_multiple=r_multiple,
                risk_pct=risk_pct,
            )

        # Record TCA (execution quality) for fills in auto mode
        if self.context.execution_mode == "auto" and order_status in ("filled", "partially_filled"):
            self._record_tca(
                trade_id, symbol, entry_price, executed_price, order_status, shares, actual_shares, order_send_time
            )

        return order_status

    def _upsert_position_record(
        self,
        cur: PsycopgCursor[Any],
        position_id: str,
        symbol: str,
        trade_id: str,
        actual_shares: Decimal,
        executed_price: Decimal,
        position_value: Decimal,
        position_status: str,
        entry_date: Any,
        stop_loss_price: Decimal,
        target_1_price: Decimal | None,
        target_2_price: Decimal | None,
        target_3_price: Decimal | None,
        r_multiple: float | None,
        risk_pct: float | None,
    ) -> None:
        """Insert a new algo_positions row, or update/reopen an existing one, for _record_entry_phase."""
        try:
            # Check if position already exists (from reuse logic above)
            check_exists_sql = "SELECT position_id FROM algo_positions WHERE position_id = %s"
            cur.execute(check_exists_sql, (position_id,))
            existing_position = cur.fetchone()

            if existing_position:
                # Position exists - fetch current status to determine if reopening or adding
                cur.execute("SELECT trade_ids_arr, status FROM algo_positions WHERE position_id = %s", (position_id,))
                fetch_result = cur.fetchone()
                existing_trades_result = fetch_result
                existing_status = fetch_result[1] if fetch_result and len(fetch_result) > 1 else None

                is_reopening_closed_position = existing_status == "closed"
                if is_reopening_closed_position:
                    logger.warning(
                        f"[POSITION REOPEN] {symbol}: Reopening CLOSED position "
                        f"(position_id={position_id}, trade_id={trade_id}). "
                        f"Will reset current_stop_price to new stop_loss_price."
                    )
                else:
                    logger.info(
                        f"[POSITION UPDATE] {symbol}: Adding to OPEN position "
                        f"(position_id={position_id}, trade_id={trade_id}). "
                        f"Will preserve existing current_stop_price."
                    )

                # Fetch existing trade_ids_arr to append new trade_id
                existing_trades_arr = (
                    existing_trades_result[0] if existing_trades_result and existing_trades_result[0] else []
                )
                # Append new trade_id if not already present
                updated_trades_arr = list(existing_trades_arr) if existing_trades_arr else []
                if trade_id not in updated_trades_arr:
                    updated_trades_arr.append(trade_id)
                trade_ids_text = ",".join(updated_trades_arr) if updated_trades_arr else None

                if is_reopening_closed_position:
                    # Reopening closed position: reset current_stop_price to new stop_loss_price
                    cur.execute(
                        """
                        UPDATE algo_positions
                        SET quantity = %s, avg_entry_price = %s, entry_price = %s,
                            current_price = %s, position_value = %s,
                            unrealized_pnl = %s, unrealized_pnl_pct = %s,
                            status = %s, entry_date = %s, trade_ids = %s,
                            trade_ids_arr = %s, current_stop_price = %s, stop_loss_price = %s,
                            target_1_price = %s, target_2_price = %s, target_3_price = %s,
                            target_1_r_multiple = %s, target_2_r_multiple = %s, target_3_r_multiple = %s,
                            r_multiple = %s, risk_pct = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE position_id = %s
                        """,
                        (
                            actual_shares,
                            executed_price,
                            executed_price,
                            executed_price,
                            position_value,
                            0,
                            0,
                            position_status,
                            entry_date,
                            trade_ids_text,
                            updated_trades_arr,
                            stop_loss_price,
                            stop_loss_price,
                            target_1_price,
                            target_2_price,
                            target_3_price,
                            self.t1_target_r_multiple if target_1_price else None,
                            self.t2_target_r_multiple if target_2_price else None,
                            self.t3_target_r_multiple if target_3_price else None,
                            r_multiple,
                            risk_pct,
                            position_id,
                        ),
                    )
                else:
                    # Adding to open position: preserve current_stop_price
                    cur.execute(
                        """
                        UPDATE algo_positions
                        SET quantity = %s, avg_entry_price = %s, entry_price = %s,
                            current_price = %s, position_value = %s,
                            unrealized_pnl = %s, unrealized_pnl_pct = %s,
                            status = %s, entry_date = %s, trade_ids = %s,
                            trade_ids_arr = %s, stop_loss_price = %s,
                            target_1_price = %s, target_2_price = %s, target_3_price = %s,
                            target_1_r_multiple = %s, target_2_r_multiple = %s, target_3_r_multiple = %s,
                            r_multiple = %s, risk_pct = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE position_id = %s
                        """,
                        (
                            actual_shares,
                            executed_price,
                            executed_price,
                            executed_price,
                            position_value,
                            0,
                            0,
                            position_status,
                            entry_date,
                            trade_ids_text,
                            updated_trades_arr,
                            stop_loss_price,
                            target_1_price,
                            target_2_price,
                            target_3_price,
                            self.t1_target_r_multiple if target_1_price else None,
                            self.t2_target_r_multiple if target_2_price else None,
                            self.t3_target_r_multiple if target_3_price else None,
                            r_multiple,
                            risk_pct,
                            position_id,
                        ),
                    )
                logger.info(
                    f"[POSITION UPDATE] Successfully reopened position for {symbol} "
                    f"(position_id={position_id}, trade_id={trade_id})"
                )
            else:
                # Position doesn't exist - INSERT new position
                logger.debug(
                    f"[POSITION INSERT] About to insert position for {symbol} "
                    f"(position_id={position_id}, trade_id={trade_id})"
                )
                cur.execute(
                    """
                    INSERT INTO algo_positions (
                        position_id, symbol, quantity, avg_entry_price, entry_price,
                        current_price, position_value, unrealized_pnl, unrealized_pnl_pct,
                        status, entry_date, trade_ids,
                        trade_ids_arr, current_stop_price, stop_loss_price, target_levels_hit,
                        target_1_price, target_2_price, target_3_price,
                        target_1_r_multiple, target_2_r_multiple, target_3_r_multiple,
                        r_multiple, risk_pct, cognito_sub, metrics_updated_at, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, 0, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """,
                    (
                        position_id,
                        symbol,
                        actual_shares,
                        executed_price,
                        executed_price,
                        executed_price,
                        position_value,
                        # unrealized_pnl/pct at the instant of entry are trivially 0 (current_price
                        # == executed_price, no movement yet) - same reasoning as r_multiple below.
                        # Leaving these NULL (the prior behavior - neither column has a DB default)
                        # meant a freshly-entered position had NULL unrealized_pnl until the next
                        # Phase 3 (position_monitor) run updated it. Phase 2 (circuit breakers) runs
                        # BEFORE Phase 3 on every run, so the sector-drawdown circuit breaker's
                        # fail-closed NULL check - correct for genuinely missing data - crashed and
                        # halted the entire orchestrator on every run immediately following any
                        # entry. Live-reproduced 2026-07-27: NBBK entered in one run, the very next
                        # run's Phase 2 halted on "Sector drawdown check: position missing P&L/
                        # cost-basis data (sector=Financial Services)", cascading into exit_engine
                        # running in Phase-5-halted degraded mode and Phase 9 reconciliation halting
                        # trading entirely.
                        0,
                        0,
                        position_status,
                        entry_date,
                        trade_id,
                        [trade_id],
                        stop_loss_price,
                        stop_loss_price,
                        target_1_price,
                        target_2_price,
                        target_3_price,
                        self.t1_target_r_multiple if target_1_price else None,
                        self.t2_target_r_multiple if target_2_price else None,
                        self.t3_target_r_multiple if target_3_price else None,
                        r_multiple,
                        risk_pct,
                        get_algo_owner_cognito_sub(),
                    ),
                )
                logger.info(
                    f"[POSITION INSERT] Successfully inserted position for {symbol} "
                    f"(position_id={position_id}, trade_id={trade_id})"
                )
        except Exception as pos_err:
            logger.critical(
                f"[POSITION INSERT CRITICAL] FAILED to insert/update position for {symbol}: "
                f"{type(pos_err).__name__}: {pos_err} "
                f"(position_id={position_id}, trade_id={trade_id}). "
                f"Transaction will rollback - trade {trade_id} WILL NOT PERSIST",
                exc_info=True,
            )
            raise

    def _notify_entry_phase(
        self,
        symbol: str,
        shares: Decimal,
        executed_price: Decimal | float,
        stop_loss_price: Decimal | float,
        target_1_price: Decimal | None,
        base_type: str | None,
        trade_id: str,
    ) -> None:
        """PHASE 4: Send entry notification."""
        self._send_entry_notification(
            symbol, shares, executed_price, stop_loss_price, target_1_price, base_type, trade_id
        )

    def _send_entry_notification(
        self,
        symbol: str,
        shares: Decimal,
        executed_price: Decimal | float,
        stop_loss_price: Decimal | float,
        target_1_price: Decimal | None,
        base_type: str | None,
        trade_id: str,
    ) -> None:
        """Send trade entry notification. Best-effort - must never fail the entry.

        CRITICAL FIX: this used to re-raise on any notification failure under a
        "FAIL-FAST, must not proceed with the trade" rationale. That rationale only
        holds if the check runs BEFORE the trade happens - but this method is PHASE 4
        of _execute_entry_txn, called after PHASE 2 (order submission - in auto mode, a
        REAL Alpaca buy that has already filled, an irreversible event) and PHASE 3
        (the algo_trades/algo_positions INSERT, in the SAME transaction/cursor as this
        call). By the time this runs there is nothing left to prevent: the trade has
        already happened. Re-raising here propagated out of _execute_entry_txn, out of
        the `with DatabaseContext("write") as cur:` block in _with_cursor, which rolls
        back on any exception - deleting the just-inserted algo_trades/algo_positions
        rows for a position that was already bought for real at the broker. The result:
        a fully real, broker-held position with ZERO record anywhere in the DB - not
        visible to any stop-loss, risk check, circuit breaker, or exit path, since none
        of them know it exists. (The old comment even said "Trade record created but
        trader was NOT alerted" immediately before raising - an explicit admission the
        record already existed when this discarded it.) Mirrors the identical fix
        already applied to ExitHandler._execute_exit's notification block - a
        notification delivery problem must never revert a trade that already happened.
        """
        try:
            config_dict = self.config.to_dict() if hasattr(self.config, "to_dict") else self.config
            notif_service = TradeNotificationService(config_dict)
            notif_service._send_notification(
                subject=f"ENTRY: {symbol}",
                message=f"{shares:.2f} sh {symbol} @ ${float(executed_price):.2f}",
                kind="trade_entry",
                severity="info",
                symbol=symbol,
                details={
                    "entry_price": float(executed_price),
                    "shares": float(shares),
                    "stop_loss": float(stop_loss_price),
                    "target_1": float(target_1_price) if target_1_price else None,
                    "base_type": base_type,
                    "trade_id": trade_id,
                },
            )
        except Exception as e:
            logger.error(
                f"[ENTRY_HANDLER] Failed to send entry notification for {symbol} trade {trade_id} "
                f"(non-blocking, trade already committed): {type(e).__name__}: {e}"
            )
