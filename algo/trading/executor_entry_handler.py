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

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import requests

from algo.reporting import TradeNotificationService, notify
from algo.trading.exceptions import (
    DatabaseError,
    NotificationError,
    OrderExecutionError,
)


logger = logging.getLogger(__name__)

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

    def __init__(self, executor: Any) -> None:
        """Initialize with reference to TradeExecutor for access to shared resources."""
        self.executor = executor
        self.config = executor.config
        self.validator = executor.validator
        self.tca = executor.tca
        self.t1_target_r_multiple = executor.t1_target_r_multiple
        self.t2_target_r_multiple = executor.t2_target_r_multiple
        self.t3_target_r_multiple = executor.t3_target_r_multiple

    def execute_entry(
        self,
        symbol: str,
        entry_price: Decimal | float,
        shares: Decimal | float,
        stop_loss_price: Decimal | float,
        target_1_price: Decimal | float | None,
        target_2_price: Decimal | float | None,
        target_3_price: Decimal | float | None,
        signal_date: Any,
        entry_date: Any,
        sqs: Any | None,
        trend_score: float | None,
        swing_score: float | None,
        swing_grade: str | None,
        base_type: str | None,
        base_quality: str | None,
        stage_phase: str | None,
        sector: str | None,
        industry: str | None,
        rs_percentile: float | None,
        market_exposure_at_entry: float | None,
        exposure_tier_at_entry: str | None,
        stop_method: str | None,
        stop_reasoning: str | None,
        swing_components: dict | None,
        advanced_components: dict | None,
    ) -> dict[str, Any]:
        """Execute entry trade with all validations and database operations.

        Returns: {
            'success': bool,
            'trade_id': str,
            'alpaca_order_id': str,
            'status': str,
            'message': str,
        }
        """
        # Convert types to Decimal for precision
        entry_price = Decimal(str(entry_price))
        shares = Decimal(str(shares))
        stop_loss_price = Decimal(str(stop_loss_price))
        if target_1_price is not None:
            target_1_price = Decimal(str(target_1_price))
        if target_2_price is not None:
            target_2_price = Decimal(str(target_2_price))
        if target_3_price is not None:
            target_3_price = Decimal(str(target_3_price))

        # Normalize dates
        if not signal_date:
            signal_date = datetime.now(timezone.utc).date()
        if not entry_date:
            entry_date = datetime.now(timezone.utc).date()

        # Validate symbol
        if not symbol:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid",
                "message": "symbol is required",
            }

        # Validate entry preconditions (prices, quantities, portfolio)
        valid, error_msg, validation_result = self.validator.validate_entry_preconditions(
            symbol=symbol,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            shares=shares,
            portfolio_value=self.executor._get_portfolio_value(),
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
        def _check_dup_pos(cur: Any) -> dict[str, str] | None:
            is_dup, msg = self.validator.check_duplicate_position(cur, symbol)
            if is_dup:
                return {"error": msg}
            return None

        try:
            dup_result = self.executor._with_cursor(_check_dup_pos)
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
        def _execute_entry_txn(cur: Any) -> dict[str, Any]:
            """Execute entry transaction with database locks."""
            # Local variables for this transaction (converted to Decimal for type safety)
            tgt_1_price: Decimal | None = Decimal(str(target_1_price)) if target_1_price else None
            tgt_2_price: Decimal | None = Decimal(str(target_2_price)) if target_2_price else None
            tgt_3_price: Decimal | None = Decimal(str(target_3_price)) if target_3_price else None

            # Validate entry conditions within transaction
            is_valid, error_msg, error_details = self.executor._validate_entry_conditions(
                cur, symbol, signal_date, entry_price, stop_loss_price
            )
            if not is_valid:
                result: dict[str, Any] = {
                    "success": False,
                    "trade_id": error_details["trade_id"] if error_details else "",
                    "message": error_msg,
                }
                if error_details:
                    result.update({k: v for k, v in error_details.items() if k != "trade_id"})
                return result

            # Generate trade ID and submit order
            trade_id = f"TRD-{uuid.uuid4().hex[:10].upper()}"
            execution_mode = self.executor.execution_mode

            order_ok, alpaca_order_id, order_status, order_error, executed_price, rejection_reason = (
                self.executor._submit_and_validate_order(
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
                return {
                    "success": False,
                    "trade_id": trade_id,
                    "status": "failed",
                    "message": order_error,
                }

            # Verify bracket orders in auto mode
            if execution_mode == "auto":
                has_last_order = hasattr(self.executor, "_last_order_result")
                order_result = self.executor._last_order_result if has_last_order else None
                if order_result is None:
                    return {
                        "success": False,
                        "trade_id": trade_id,
                        "status": "failed",
                        "message": "Order result missing - bracket validation failed",
                    }
                legs = order_result.get("legs", [])
                if order_result.get("order_class") == "bracket" and len(legs) < 2:
                    try:
                        self.executor._cancel_bracket_orders(alpaca_order_id)
                    except (OrderExecutionError, DatabaseError, requests.RequestException, requests.Timeout) as e:
                        logger.warning(f"Failed to cancel bracket order {alpaca_order_id}: {e}")
                    return {
                        "success": False,
                        "trade_id": trade_id,
                        "status": "failed",
                        "message": f"Bracket order missing stop loss leg ({len(legs)} legs)",
                    }

                # Check for order rejection/cancellation
                if order_status in ("rejected", "cancelled", "expired"):
                    try:
                        notify(
                            "critical",
                            title=f"Order {order_status.upper()}: {symbol}",
                            message=f"Trade {trade_id}: {shares}sh @ ${entry_price:.2f}",
                        )
                    except NotificationError as e:
                        logger.warning(f"Failed to send rejection alert: {e}")
                    return {
                        "success": False,
                        "trade_id": trade_id,
                        "status": order_status,
                        "message": f"Alpaca {order_status} order: {symbol}",
                    }

            # Handle slippage: recalculate targets if fill price differs from signal
            if executed_price and executed_price != entry_price:
                tgt_1_price, tgt_2_price, tgt_3_price = self._recalculate_targets_for_slippage(
                    executed_price, entry_price, stop_loss_price
                )

            # Calculate position size percentage
            pv_for_pct = self.executor._get_portfolio_value()
            position_size_pct = self._calculate_position_size_pct(shares, executed_price or entry_price, pv_for_pct)

            # Build entry reason
            entry_reason = self._build_entry_reason(swing_grade, base_type, stage_phase, exposure_tier_at_entry)

            # Insert trade record
            self._insert_trade_record(
                cur, trade_id, idempotency_key, symbol, signal_date, entry_date,
                executed_price, shares, entry_reason, stop_loss_price, stop_method,
                tgt_1_price, tgt_2_price, tgt_3_price,
                order_status, execution_mode, alpaca_order_id,
                position_size_pct, sqs, trend_score, swing_score, swing_grade,
                base_type, base_quality, stage_phase,
                sector, industry, rs_percentile,
                market_exposure_at_entry, exposure_tier_at_entry,
                stop_reasoning, swing_components, advanced_components,
                rejection_reason
            )

            # Insert position record if order was filled
            if order_status in ("filled", "partially_filled"):
                if execution_mode == "auto" and alpaca_order_id:
                    verified_status = self.executor._verify_order_status(alpaca_order_id)
                    if verified_status not in ("filled", "partially_filled"):
                        return {
                            "success": False,
                            "trade_id": trade_id,
                            "status": verified_status or "unknown",
                            "message": f"Order status changed from {order_status} to {verified_status}",
                        }
                    order_status = verified_status

                actual_shares = shares
                if order_status == "partially_filled" and alpaca_order_id:
                    filled_qty = self.executor._get_order_filled_quantity(alpaca_order_id)
                    if filled_qty and filled_qty > 0:
                        actual_shares = filled_qty
                        logger.info(_redact_for_logs(f"Partial fill: {actual_shares} of {shares} shares"))

                # Validate position value
                position_value = Decimal(str(actual_shares)) * Decimal(str(executed_price))
                if position_value <= 0:
                    return {
                        "success": False,
                        "trade_id": trade_id,
                        "status": "invalid",
                        "message": f"Invalid position value: {actual_shares} @ ${executed_price:.2f}",
                    }

                # Insert position record
                position_id = f"POS-{trade_id}"
                cur.execute(
                    """
                    INSERT INTO algo_positions (
                        position_id, symbol, quantity, avg_entry_price,
                        current_price, position_value, status,
                        trade_ids_arr, current_stop_price, stop_loss_price, target_levels_hit,
                        created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, 'open',
                        %s, %s, %s, 0, CURRENT_TIMESTAMP
                    )
                    """,
                    (
                        position_id, symbol, actual_shares, executed_price,
                        executed_price, position_value,
                        [trade_id], stop_loss_price, stop_loss_price,
                    ),
                )

            # Record TCA (execution quality) for fills in auto mode
            if self.executor.execution_mode == "auto" and order_status in ("filled", "partially_filled"):
                self._record_tca(trade_id, symbol, entry_price, executed_price, order_status)

            # Send entry notification
            self._send_entry_notification(
                symbol, shares, executed_price or entry_price, stop_loss_price,
                tgt_1_price, swing_score, base_type, trade_id
            )

            return {
                "success": True,
                "trade_id": trade_id,
                "alpaca_order_id": alpaca_order_id,
                "status": order_status,
                "message": f"{shares} sh {symbol} @ ${(executed_price or entry_price):.2f}",
            }

        # Execute entry transaction with locks
        try:
            return self.executor._with_cursor(_execute_entry_txn, acquire_locks=True)  # type: ignore[no-any-return]
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
        """Calculate position size as percentage of portfolio."""
        if portfolio_value is None or portfolio_value <= 0:
            logger.warning("Portfolio value unavailable for position size calculation")
            return None

        position_size = (
            (Decimal(shares) * Decimal(str(price)) / Decimal(str(portfolio_value)) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
        return position_size

    def _build_entry_reason(
        self, swing_grade: str | None, base_type: str | None, stage_phase: str | None, exposure_tier: str | None
    ) -> str:
        """Build comprehensive entry reason string."""
        parts = ["Algo signal - all tiers passed"]
        if swing_grade:
            parts.append(f"swing_grade={swing_grade}")
        if base_type:
            parts.append(f"base={base_type}")
        if stage_phase:
            parts.append(f"phase={stage_phase}")
        if exposure_tier:
            parts.append(f"exposure={exposure_tier}")
        return " | ".join(parts)

    def _insert_trade_record(
        self, cur: Any, trade_id: str, idempotency_key: str, symbol: str, signal_date: Any, entry_date: Any,
        executed_price: Decimal | None, shares: Decimal, entry_reason: str, stop_loss_price: Decimal,
        stop_method: str | None, target_1_price: Decimal | None, target_2_price: Decimal | None,
        target_3_price: Decimal | None, order_status: str, execution_mode: str, alpaca_order_id: str,
        position_size_pct: Decimal | None, sqs: Any, trend_score: float | None, swing_score: float | None,
        swing_grade: str | None, base_type: str | None, base_quality: str | None, stage_phase: str | None,
        sector: str | None, industry: str | None, rs_percentile: float | None,
        market_exposure_at_entry: float | None, exposure_tier_at_entry: str | None,
        stop_reasoning: str | None, swing_components: dict | None, advanced_components: dict | None,
        rejection_reason: str | None,
    ) -> None:
        """Insert trade record into database."""
        cur.execute(
            """
            INSERT INTO algo_trades (
                trade_id, idempotency_key, symbol, signal_date, trade_date,
                entry_time, entry_price, entry_quantity, entry_reason,
                stop_loss_price, stop_loss_method,
                target_1_price, target_1_r_multiple,
                target_2_price, target_2_r_multiple,
                target_3_price, target_3_r_multiple,
                status, execution_mode, alpaca_order_id,
                position_size_pct, signal_quality_score, trend_template_score,
                swing_score, swing_grade,
                base_type, base_quality, stage_phase, entry_stage,
                sector, industry, rs_percentile,
                market_exposure_at_entry, exposure_tier_at_entry,
                stop_method, stop_reasoning,
                swing_components, advanced_components, bracket_order,
                reentry_count, prior_trade_id, rejection_reason,
                created_at
            ) VALUES (
                %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                CURRENT_TIMESTAMP
            )
            """,
            (
                trade_id, idempotency_key, symbol, signal_date, entry_date,
                executed_price, shares, entry_reason,
                stop_loss_price, stop_method or "minervini_break_or_swing_low",
                target_1_price, self.t1_target_r_multiple,
                target_2_price, self.t2_target_r_multiple,
                target_3_price, self.t3_target_r_multiple,
                order_status, execution_mode, alpaca_order_id,
                position_size_pct,
                float(sqs) if sqs is not None else None,
                float(trend_score) if trend_score is not None else None,
                swing_score, swing_grade,
                base_type, base_quality,
                STAGE_PHASE_MAPPING.get(stage_phase) if stage_phase else None, stage_phase,
                sector, industry, rs_percentile,
                market_exposure_at_entry, exposure_tier_at_entry,
                stop_method, stop_reasoning,
                json.dumps(swing_components) if swing_components else None,
                json.dumps(advanced_components) if advanced_components else None,
                execution_mode == "auto",
                0, None, rejection_reason,
            ),
        )

    def _record_tca(
        self, trade_id: str, symbol: str, entry_price: Decimal,
        executed_price: Decimal | None, order_status: str
    ) -> None:
        """Record trade cost analysis (execution quality)."""
        try:
            if not hasattr(self.executor, "_order_send_time"):
                raise RuntimeError(f"[TCA CRITICAL] {symbol}: _order_send_time not set")

            execution_latency_ms = int((time.time() - self.executor._order_send_time) * 1000)
            if execution_latency_ms < 0:
                raise ValueError(f"[TCA CRITICAL] {symbol}: negative latency {execution_latency_ms}ms")

            tca_result = self.tca.record_fill(
                trade_id=trade_id,
                symbol=symbol,
                signal_price=float(entry_price),
                fill_price=float(executed_price) if executed_price else float(entry_price),
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
                    logger.warning(f"Failed to send TCA alert: {e}")
        except DatabaseError as e:
            logger.warning(f"TCA recording failed: {e}")

    def _send_entry_notification(
        self, symbol: str, shares: Decimal, executed_price: Decimal | float,
        stop_loss_price: Decimal | float, target_1_price: Decimal | None,
        swing_score: float | None, base_type: str | None, trade_id: str
    ) -> None:
        """Send trade entry notification."""
        try:
            notif_service = TradeNotificationService()
            notif_service._send_notification(
                subject=f"ENTRY: {symbol}",
                message=f"{shares:.2f} sh {symbol} @ ${float(executed_price):.2f}",
                kind="trade_entry",
                severity="info",
                symbol=symbol,
                details={
                    "entry_price": executed_price,
                    "shares": float(shares),
                    "stop_loss": stop_loss_price,
                    "target_1": target_1_price,
                    "swing_score": swing_score,
                    "base_type": base_type,
                    "trade_id": trade_id,
                },
            )
        except NotificationError as e:
            logger.warning(f"Failed to send entry notification: {e}")
