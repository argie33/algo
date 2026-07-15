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

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date as _date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

import requests
from psycopg2.extensions import cursor as PsycopgCursor

from algo.reporting import TradeNotificationService, notify
from algo.trading.exceptions import (
    DatabaseError,
    NotificationError,
    OrderExecutionError,
)
from algo.trading.handler_context import HandlerContext
from algo.trading.trade_context import TradeContext

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
            is_dup, msg = self.validator.check_duplicate_position(cur, symbol)
            if is_dup:
                return {"error": msg}
            logger.debug(f"[ENTRY_HANDLER] No duplicate position found for {symbol}, can proceed")
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

        # Generate idempotency key
        import hashlib

        key_source = f"{symbol}|{signal_date}|{entry_price}|{stop_loss_price}"
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

            # Generate trade ID and prepare for submission
            trade_id = f"TRD-{uuid.uuid4().hex[:10].upper()}"
            execution_mode = self.context.execution_mode

            # PHASE 2: Submit
            order_ok, order_error, order_status, alpaca_order_id, executed_price, rejection_reason = (
                self._submit_entry_phase(
                    cur,
                    symbol,
                    trade_id,
                    shares,
                    entry_price,
                    stop_loss_price,
                    tgt_1_price,
                    execution_mode,
                )
            )
            if not order_ok:
                # PAPER MODE GRACEFUL DEGRADATION: In paper trading, still create trade record
                # even if Alpaca submission fails (connection, auth, etc.)
                # This ensures trades are tracked for backtesting and portfolio management
                if execution_mode in ("paper", "auto"):
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
                    # Live mode: Alpaca failure is a hard stop
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
                slippage_pct = abs((executed_price - entry_price) / entry_price * 100)
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

        position_size = (Decimal(shares) * Decimal(str(price)) / Decimal(str(portfolio_value)) * Decimal(100)).quantize(
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
        """Insert trade record into database."""
        cur.execute(
            """
            INSERT INTO algo_trades (
                trade_id, idempotency_key, symbol, signal_date, trade_date, entry_date,
                entry_time, entry_price, entry_quantity, quantity, entry_reason,
                stop_loss_price, stop_loss_method,
                target_1_price, target_1_r_multiple,
                target_2_price, target_2_r_multiple,
                target_3_price, target_3_r_multiple,
                status, execution_mode, alpaca_order_id,
                position_id, position_size_pct, signal_quality_score, trend_template_score,
                base_type, base_quality, stage_phase, entry_stage,
                sector, industry, rs_percentile,
                market_exposure_at_entry, exposure_tier_at_entry,
                stop_method, stop_reasoning,
                advanced_components, bracket_order,
                reentry_count, prior_trade_id, rejection_reason,
                created_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (symbol, signal_date, entry_price) DO NOTHING
            """,
            (
                request.trade_id,
                request.idempotency_key,
                request.symbol,
                request.signal_date,
                request.entry_date,
                request.entry_date,
                request.executed_price,
                request.shares,
                request.shares,  # CRITICAL FIX: Add quantity = entry_quantity for all new trades
                request.entry_reason,
                request.stop_loss_price,
                request.stop_method or "minervini_break_or_swing_low",
                request.target_1_price,
                self.t1_target_r_multiple,
                request.target_2_price,
                self.t2_target_r_multiple,
                request.target_3_price,
                self.t3_target_r_multiple,
                request.order_status,
                request.execution_mode,
                request.alpaca_order_id,
                request.position_id,  # FIXED: Link trade to position
                request.position_size_pct,
                float(request.sqs) if request.sqs is not None else None,
                float(request.trend_score) if request.trend_score is not None else None,
                request.base_type,
                request.base_quality,
                self._validate_stage_phase(request.stage_phase),
                request.stage_phase,
                request.sector,
                request.industry,
                request.rs_percentile,
                request.market_exposure_at_entry,
                request.exposure_tier_at_entry,
                request.stop_method,
                request.stop_reasoning,
                json.dumps(request.advanced_components) if request.advanced_components else None,
                request.execution_mode == "auto",
                0,
                None,
                request.rejection_reason,
            ),
        )

    def _record_tca(
        self,
        trade_id: str,
        symbol: str,
        entry_price: Decimal,
        executed_price: Decimal | None,
        order_status: str,
    ) -> None:
        """Record trade cost analysis (execution quality)."""
        try:
            # _order_send_time is set by the order submission logic
            execution_latency_ms = int((time.time() - self.context._order_send_time) * 1000)  # type: ignore[attr-defined]
            if execution_latency_ms < 0:
                raise ValueError(f"[TCA CRITICAL] {symbol}: negative latency {execution_latency_ms}ms")

            tca_result = self.tca.record_fill(
                trade_id=trade_id,
                symbol=symbol,
                signal_price=entry_price,
                fill_price=(executed_price if executed_price else entry_price),
                shares_requested=1,
                shares_filled=1,
                side="BUY",
                execution_latency_ms=execution_latency_ms,
            )

            # Alert if slippage excessive
            if "alert" in tca_result:
                try:
                    alert_data = tca_result["alert"]
                    notify(
                        alert_data["severity"].lower(),
                        title=f"TCA Alert: {alert_data['severity']}",
                        message=alert_data["message"],
                    )
                except NotificationError as e:
                    raise RuntimeError(
                        f"CRITICAL: Failed to send TCA alert notification: {e}. "
                        f"Trade Cost Analysis data may not reach monitoring systems. "
                        f"Trader was not notified of trade {trade_id}."
                    ) from e
        except DatabaseError as e:
            raise RuntimeError(
                f"CRITICAL: Failed to record TCA data for trade {trade_id}: {e}. "
                f"Trade Cost Analysis audit trail lost. Cannot proceed without recording."
            ) from e

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
    ) -> tuple[bool, str, str, str, Decimal | None, str | None]:
        """PHASE 2: Submit order and validate result."""
        order_ok, alpaca_order_id, order_status, order_error, executed_price, rejection_reason = (
            self.context._submit_and_validate_order(
                symbol,
                trade_id,
                shares,
                entry_price,
                stop_loss_price,
                target_1_price,
                execution_mode,
            )
        )

        if not order_ok:
            return False, order_error, "", "", None, rejection_reason

        # Verify bracket orders in auto mode
        if execution_mode == "auto":
            # _last_order_result is set by order submission logic
            order_result = self.context._last_order_result  # type: ignore[attr-defined]
            if order_result is None:
                return (
                    False,
                    "Order result missing - bracket validation failed",
                    "",
                    "",
                    None,
                    rejection_reason,
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

            if order_class == "bracket" and len(legs) < 2:
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
                )

            # Check for order rejection/cancellation
            if order_status in ("rejected", "cancelled", "expired"):
                try:
                    notify(
                        "critical",
                        title=f"Order {order_status.upper()}: {symbol}",
                        message=f"Trade {trade_id}: {shares}sh @ ${entry_price:.2f}",
                    )
                except NotificationError as e:
                    raise RuntimeError(
                        f"CRITICAL: Failed to send rejection alert for {symbol} (order {order_status}): {e}. "
                        f"Trader was NOT notified that order was {order_status}."
                    ) from e
                return (
                    False,
                    f"Alpaca {order_status} order: {symbol}",
                    order_status,
                    "",
                    None,
                    rejection_reason,
                )

        return True, "", order_status, alpaca_order_id, executed_price, rejection_reason

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
    ) -> str:
        """PHASE 3: Insert trade record, position record, record TCA."""
        if executed_price is None:
            raise ValueError(
                f"[ENTRY_HANDLER CRITICAL] {symbol}: Recording entry without executed_price. "
                f"Cannot calculate position size percentage or record accurate cost basis."
            )

        # Generate position_id upfront so it can be linked in both trade and position records
        import uuid

        position_id = str(uuid.uuid4())

        # Calculate position size percentage
        pv_for_pct = self.context._get_portfolio_value()
        position_size_pct = self._calculate_position_size_pct(shares, executed_price, pv_for_pct)

        entry_reason = self._build_entry_reason(
            context.signals.base_type,
            context.signals.stage_phase,
            context.market.exposure_tier_at_entry,
        )

        trade_request = TradeInsertionRequest(
            trade_id=trade_id,
            idempotency_key=idempotency_key,
            symbol=symbol,
            signal_date=context.signal_date,
            entry_date=context.entry_date,
            executed_price=executed_price,
            shares=shares,
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
            # Only link to a position when one will actually be created below (order_status
            # in filled/partially_filled/paper_pending/open - "open" is the immediate
            # simulated-fill status used by paper/dry execution_mode). The FK is DEFERRABLE
            # INITIALLY DEFERRED so the position row (inserted after this trade row, same
            # transaction) satisfies it by commit time, but a trade whose order didn't fill
            # (e.g. "pending" in review mode) has no corresponding position ever, so
            # position_id must stay NULL for those.
            position_id=position_id
            if order_status in ("filled", "partially_filled", "paper_pending", "open")
            else None,
        )
        self._insert_trade_record(cur, trade_request)

        # Insert position record if order was filled or paper_pending (paper mode tracking)
        # PAPER MODE: Create positions for paper_pending trades to maintain portfolio state
        # Live mode: Only create positions for actual filled/partially_filled orders
        if order_status in ("filled", "partially_filled", "paper_pending", "open"):
            # Use the position_id from trade_request to link position to trade
            position_id = trade_request.position_id or str(uuid.uuid4())
            entry_date = context.entry_date

            if self.context.execution_mode == "auto" and alpaca_order_id:
                verified_status = self.context._verify_order_status(alpaca_order_id)
                if verified_status is None:
                    raise OrderExecutionError(
                        f"Order {alpaca_order_id}: verification failed (status is None). "
                        f"Cannot record position without verified fill status. "
                        f"This indicates Alpaca API communication error or order data corruption."
                    )
                elif verified_status not in ("filled", "partially_filled"):
                    return str(verified_status)
                else:
                    order_status = verified_status

            actual_shares = shares
            if order_status == "partially_filled" and alpaca_order_id:
                filled_qty = self.context._get_order_filled_quantity(alpaca_order_id)
                if filled_qty is not None and filled_qty > 0:
                    actual_shares = filled_qty
                    logger.info(_redact_for_logs(f"Partial fill: {actual_shares} of {shares} shares"))

            # Validate position value
            position_value = Decimal(str(actual_shares)) * Decimal(str(executed_price))
            if position_value <= 0:
                return "invalid"

            # CRITICAL VALIDATION: entry_price and entry_date must NEVER be NULL
            if executed_price is None or entry_date is None:
                raise ValueError(
                    f"[POSITION_CREATION CRITICAL] {symbol}: Cannot create position with NULL entry_price or entry_date. "
                    f"executed_price={executed_price}, entry_date={entry_date}. "
                    f"Portfolio reconciliation depends on having entry prices for all positions."
                )

            # Use the position_id that was created when inserting the trade
            # This ensures trade and position are linked via foreign key
            # CRITICAL: Paper_pending trades MUST create open positions for portfolio tracking
            # This ensures paper mode trading maintains accurate position state
            position_status = "paper_open" if order_status == "paper_pending" else "open"

            # Calculate R-multiple for risk metrics (entry - stop) for accurate risk assessment
            r_multiple = None
            if stop_loss_price and executed_price:
                risk_per_share = executed_price - stop_loss_price
                if risk_per_share > 0:
                    r_multiple = 1.0  # 1R baseline; actual targets provide specific R values

            cur.execute(
                """
                INSERT INTO algo_positions (
                    position_id, symbol, quantity, avg_entry_price, entry_price,
                    current_price, position_value, status, entry_date,
                    trade_ids_arr, current_stop_price, stop_loss_price, target_levels_hit,
                    target_1_price, target_2_price, target_3_price,
                    target_1_r_multiple, target_2_r_multiple, target_3_r_multiple,
                    r_multiple, metrics_updated_at, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, 0, %s, %s, %s, %s, %s, %s,
                    %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
                    position_status,
                    entry_date,
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
                ),
            )

        # Record TCA (execution quality) for fills in auto mode
        if self.context.execution_mode == "auto" and order_status in ("filled", "partially_filled"):
            self._record_tca(trade_id, symbol, entry_price, executed_price, order_status)

        return order_status

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
        """Send trade entry notification. FAIL-FAST if notification system unavailable.

        Entry notifications are CRITICAL-trader must be alerted immediately when
        position enters. If we cannot notify, we must not proceed with the trade.
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
        except NotificationError as e:
            raise RuntimeError(
                f"CRITICAL: Failed to send entry notification for {symbol} (trade {trade_id}): {e}. "
                f"Cannot complete entry without confirming trader notification. "
                f"Trade record created but trader was NOT alerted."
            ) from e
