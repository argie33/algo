#!/usr/bin/env python3
"""
Trade Executor - Execute trades via Alpaca and track positions

Features:
- Idempotent entry (no duplicate trades for same symbol on same day)
- Atomic DB transactions for entry/exit
- Partial exits with weighted-cost-basis P&L (T1 = 50%, T2 = 25%, T3 = 25%)
- R-multiple computed against actual stop loss (not a placeholder)
- Trailing stop adjustments after profit-taking levels
- Paper, dry, review, and auto execution modes
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

import requests

from algo.infrastructure import get_api_timeout
from algo.reporting import TradeNotificationService, notify
from algo.trading.exceptions import (
    AuditLogError,
    DatabaseError,
    DuplicatePositionError,
    NotificationError,
    OrderExecutionError,
    OrderRejectedError,
    PortfolioValueError,
    PretradeCheckFailedError,
    TradingError,
)
from config.alpaca_config import get_alpaca_base_url
from config.credential_manager import get_alpaca_credentials
from utils.db import DatabaseContext, OptimisticLockRetry
from utils.trading import PositionStatus, TradeStatus
from utils.validation import AlpacaResponseValidator


logger = logging.getLogger(__name__)
validator = AlpacaResponseValidator()

# Map stage phase names to integer IDs for database storage
STAGE_PHASE_MAPPING = {
    "early": 1,
    "mid": 2,
    "late": 3,
}


def _redact_for_logs(message: str) -> str:
    """Redact sensitive trade data from log messages. Masks prices and shares."""
    import re

    # Mask prices: $123.45 → $***
    message = re.sub(r"\$[\d.]+", "$***", message)
    # Mask shares: 100sh → ***sh
    message = re.sub(r"(\d+)sh\b", "***sh", message)
    # Mask slippage: +1.23% → +***%
    message = re.sub(r"([+-]\d+\.\d+)%", "***%", message)
    return message


class TradeExecutor:
    """Execute trades via Alpaca and track in database."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        alpaca_creds = get_alpaca_credentials()
        self.alpaca_key = alpaca_creds["key"]
        self.alpaca_secret = alpaca_creds["secret"]
        self.alpaca_base_url = get_alpaca_base_url()

        # Explicit validation: credentials must be present and non-empty
        if not self.alpaca_key or not self.alpaca_secret or not self.alpaca_base_url:
            error_msg = (
                f"[EXECUTOR_INIT_FAILED] Missing critical Alpaca credentials: "
                f"key={'present' if self.alpaca_key else 'MISSING'} "
                f"secret={'present' if self.alpaca_secret else 'MISSING'} "
                f"url={'present' if self.alpaca_base_url else 'MISSING'}"
            )
            logger.critical(error_msg)
            raise ValueError(error_msg)

        # Wire TCA engine for execution quality tracking
        from algo.trading import TCAEngine

        self.tca = TCAEngine(config)

        # Wire pre-trade hard stops (Phase 5: independent risk layer)
        from algo.trading import PreTradeChecks

        self.pretrade = PreTradeChecks(
            config, self.alpaca_base_url, self.alpaca_key, self.alpaca_secret
        )

        # Get execution mode from config (supports both dict and AlgoConfig objects)
        execution_mode = config.get("execution_mode", "paper")
        if not execution_mode:
            execution_mode = "paper"
        execution_mode = execution_mode.lower()

        live_ack = os.getenv("ALGO_LIVE_TRADING", "").strip()
        paper_flag = os.getenv("ALPACA_PAPER_TRADING", "false").strip().lower()
        url_says_paper = "paper" in (self.alpaca_base_url or "").lower()
        live_intent = (
            execution_mode == "auto"
            and live_ack == "I_UNDERSTAND_REAL_MONEY"
            and paper_flag != "true"
            and not url_says_paper
        )

        logger.info(
            f"[EXECUTOR] mode={execution_mode} live_intent={live_intent} "
            f"({'LIVE TRADING → api.alpaca.markets' if live_intent else 'PAPER TRADING → paper-api.alpaca.markets'}) | "
            f"live_ack={'SET' if live_ack == 'I_UNDERSTAND_REAL_MONEY' else 'NOT SET'} "
            f"paper_flag={paper_flag} url_says_paper={url_says_paper} "
            f"key_set={bool(self.alpaca_key)} secret_set={bool(self.alpaca_secret)}"
        )

        if not live_intent:
            # Force paper trading — CRITICAL: explicitly use paper URL, ignore APCA_API_BASE_URL
            self.alpaca_base_url = "https://paper-api.alpaca.markets"
            self.is_paper = True
            if execution_mode == "auto":
                # execution_mode is auto but live_intent is False — log exactly why
                reasons = []
                if live_ack != "I_UNDERSTAND_REAL_MONEY":
                    reasons.append(
                        f"ALGO_LIVE_TRADING not set to 'I_UNDERSTAND_REAL_MONEY' (got '{live_ack}')"
                    )
                if paper_flag == "true":
                    reasons.append("ALPACA_PAPER_TRADING=true")
                if url_says_paper:
                    reasons.append(
                        f"APCA_API_BASE_URL contains 'paper': {self.alpaca_base_url}"
                    )
                logger.warning(
                    f"[EXECUTOR] execution_mode=auto but forced to PAPER. Reason(s): {'; '.join(reasons) or 'unknown'}"
                )
        else:
            self.is_paper = False

    def _with_cursor(self, operation) -> Any:
        """Execute an operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext("write") as cur:
                return operation(cur)
        except Exception as e:
            logger.debug(f"Database operation failed: {e}")
            raise

    # ---------- Entry ----------

    def execute_trade(
        self,
        symbol: str,
        entry_price: float,
        shares: float,
        stop_loss_price: float,
        target_1_price: float | None = None,
        target_2_price: float | None = None,
        target_3_price: float | None = None,
        signal_date: Any | None = None,
        entry_date: Any | None = None,
        sqs: Any | None = None,
        trend_score: float | None = None,
        swing_score: float | None = None,
        swing_grade: str | None = None,
        base_type: str | None = None,
        base_quality: str | None = None,
        stage_phase: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        rs_percentile: float | None = None,
        market_exposure_at_entry: float | None = None,
        exposure_tier_at_entry: str | None = None,
        stop_method: str | None = None,
        stop_reasoning: str | None = None,
        swing_components: dict | None = None,
        advanced_components: dict | None = None,
    ) -> dict[str, Any]:
        """Execute a new entry trade.

        Returns: {
            'success': bool,
            'trade_id': str,
            'alpaca_order_id': str,
            'status': str,
            'message': str,
            'duplicate': bool (only when blocked by idempotency)
        }
        """
        if not signal_date:
            signal_date = datetime.now(timezone.utc).date()
        if not entry_date:
            entry_date = datetime.now(timezone.utc).date()

        if entry_date < signal_date:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid",
                "message": f"Invalid: entry_date {entry_date} must be >= signal_date {signal_date}",
            }
        # Note: entry_date == signal_date is allowed (signal fires at market open, entry happens same day)

        if not entry_price or entry_price <= 0:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid",
                "message": f"Invalid entry price: {entry_price} (must be > 0)",
            }
        if not stop_loss_price or stop_loss_price <= 0:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid",
                "message": f"Invalid stop loss price: {stop_loss_price} (must be > 0)",
            }
        if not shares or shares <= 0:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid",
                "message": f"Invalid share count: {shares} (must be > 0)",
            }

        # Phase 5: Run independent pre-trade hard stops BEFORE anything else
        portfolio_value = self._get_portfolio_value()
        if not portfolio_value or portfolio_value <= 0:
            logger.error(
                f"execute_trade: cannot determine portfolio value for {symbol}, aborting"
            )
            return {
                "success": False,
                "trade_id": "",
                "status": "portfolio_value_unavailable",
                "message": "Cannot execute trade: portfolio value unavailable from Alpaca and DB snapshot",
            }
        position_value = float(Decimal(shares) * Decimal(str(entry_price)))
        try:
            pretrade_passed, pretrade_reason = self.pretrade.run_all(
                symbol=symbol,
                position_value=position_value,
                portfolio_value=portfolio_value,
                side="BUY",
            )
        except ValueError as e:
            logger.error(f"Pre-trade validation failed with critical error: {e}")
            return {
                "success": False,
                "trade_id": "",
                "status": "pretrade_check_failed",
                "message": f"Pre-trade check failed: {e!s}",
            }
        if not pretrade_passed:
            return {
                "success": False,
                "trade_id": "",
                "status": "pretrade_check_failed",
                "message": f"Pre-trade check failed: {pretrade_reason}",
            }

        # P2 FIX: IDEMPOTENCY CHECK - Prevent duplicate positions on same symbol
        def _check_duplicate_position(cur):
            cur.execute(
                """
                SELECT symbol FROM algo_positions
                WHERE symbol = %s AND status = %s
                LIMIT 1
                """,
                (symbol, PositionStatus.OPEN.value),
            )
            return cur.fetchone()

        try:
            existing_pos = self._with_cursor(_check_duplicate_position)
            if existing_pos:
                return {
                    "success": False,
                    "trade_id": "",
                    "status": "duplicate_position",
                    "message": f"Symbol {symbol} already has an open position. Close it before entering another.",
                    "duplicate": True,
                }
        except (DatabaseError, Exception) as e:
            logger.error(f"Failed to check for duplicate position: {type(e).__name__}: {e}")
            raise DuplicatePositionError(f"Cannot verify duplicate position status: {e!s}. Order halted for safety.") from e

        # Compute targets if missing — based on R-multiples from actual stop
        # Convert to Decimal BEFORE arithmetic to avoid IEEE 754 precision loss
        entry_price_dec = Decimal(str(entry_price))
        stop_price_dec = Decimal(str(stop_loss_price))
        risk_per_share_decimal = entry_price_dec - stop_price_dec
        if risk_per_share_decimal <= 0:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid_stop",
                "message": f"Invalid stop: ${stop_loss_price:.2f} >= entry ${entry_price:.2f} (stop must be below entry)",
            }
        # Additional guard: stop must be at least 1% below entry (meaningful risk)
        if stop_price_dec >= entry_price_dec * Decimal("0.99"):
            return {
                "success": False,
                "trade_id": "",
                "status": "bad_stop",
                "message": f"Stop too tight: ${stop_loss_price:.2f} within 1% of entry ${entry_price:.2f} (meaningful R required)",
            }
        if target_1_price is None:
            t1_r = float(self.config.get("t1_target_r_multiple", 1.5))
            target_1_price = float((Decimal(str(entry_price)) + (risk_per_share_decimal * Decimal(str(t1_r)))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if target_1_price <= entry_price:
                return {
                    "success": False,
                    "trade_id": "",
                    "status": "invalid",
                    "message": f"Invalid target_1: ${target_1_price:.2f} <= entry ${entry_price:.2f}",
                }
        if target_2_price is None:
            t2_r = float(self.config.get("t2_target_r_multiple", 3.0))
            target_2_price = float((Decimal(str(entry_price)) + (risk_per_share_decimal * Decimal(str(t2_r)))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if target_2_price <= entry_price:
                return {
                    "success": False,
                    "trade_id": "",
                    "status": "invalid",
                    "message": f"Invalid target_2: ${target_2_price:.2f} <= entry ${entry_price:.2f}",
                }
        if target_3_price is None:
            t3_r = float(self.config.get("t3_target_r_multiple", 4.0))
            target_3_price = float((Decimal(str(entry_price)) + (risk_per_share_decimal * Decimal(str(t3_r)))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            if target_3_price <= entry_price:
                return {
                    "success": False,
                    "trade_id": "",
                    "status": "invalid",
                    "message": f"Invalid target_3: ${target_3_price:.2f} <= entry ${entry_price:.2f}",
                }

        # Validate target hierarchy: target_1 < target_2 < target_3
        target_1_price = float(target_1_price) if target_1_price else None
        target_2_price = float(target_2_price) if target_2_price else None
        target_3_price = float(target_3_price) if target_3_price else None
        if target_1_price and target_2_price and target_1_price >= target_2_price:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid",
                "message": f"Invalid target hierarchy: target_1 ${target_1_price:.2f} >= target_2 ${target_2_price:.2f}",
            }
        if target_2_price and target_3_price and target_2_price >= target_3_price:
            return {
                "success": False,
                "trade_id": "",
                "status": "invalid",
                "message": f"Invalid target hierarchy: target_2 ${target_2_price:.2f} >= target_3 ${target_3_price:.2f}",
            }

        import hashlib

        key_source = f"{symbol}|{signal_date}|{entry_price:.4f}|{stop_loss_price:.4f}"
        idempotency_key = hashlib.sha256(key_source.encode()).hexdigest()

        def _execute_entry(cur):
            # B10: Entire entry sequence is wrapped in a single transaction.
            # If any step fails, the transaction rolls back and no partial state is left.

            # nonlocal: allow conditional slippage recalculation to update these without
            # causing UnboundLocalError for earlier uses (Python treats any assignment in a
            # closure as local for the entire function scope).
            nonlocal target_1_price, target_2_price, target_3_price

            # Schema migration: idempotency_key now added by migration 004, not runtime
            cur.execute(
                "SELECT trade_id FROM algo_trades WHERE idempotency_key = %s LIMIT 1",
                (idempotency_key,),
            )
            existing_idempotent = cur.fetchone()
            if existing_idempotent:
                logger.warning(
                    f"DUPLICATE EXECUTION BLOCKED: Idempotency key exists for {symbol} (trade_id: {existing_idempotent[0]})"
                )
                return {
                    "success": False,
                    "trade_id": existing_idempotent[0],
                    "status": "duplicate",
                    "duplicate": True,
                    "message": f"Trade already exists for {symbol} on {signal_date} (idempotent duplicate)",
                }

            cur.execute(
                "SELECT 1 FROM algo_positions WHERE symbol = %s AND status = %s LIMIT 1",
                (symbol, PositionStatus.OPEN.value),
            )
            if cur.fetchone():
                return {
                    "success": False,
                    "trade_id": "",
                    "status": "duplicate",
                    "duplicate": True,
                    "message": f"Already have open position in {symbol}",
                }

            cur.execute(
                """
                SELECT trade_id FROM algo_trades
                WHERE symbol = %s AND COALESCE(signal_date, '1900-01-01') = COALESCE(%s, '1900-01-01')
                  AND status IN (%s, %s)
                LIMIT 1
                """,
                (
                    symbol,
                    signal_date,
                    TradeStatus.OPEN.value,
                    TradeStatus.PENDING.value,
                ),
            )
            existing = cur.fetchone()
            if existing:
                # B9: Log duplicate with visibility for pattern monitoring
                signal_fingerprint = (
                    f"{symbol}|{entry_price:.2f}|{stop_loss_price:.2f}|{signal_date}"
                )
                logger.warning(
                    f"DUPLICATE SIGNAL: {signal_fingerprint} (prior trade: {existing[0]})"
                )
                return {
                    "success": False,
                    "trade_id": existing[0],
                    "status": "duplicate",
                    "duplicate": True,
                    "message": f"Trade already exists for {symbol} on {signal_date} (fingerprint: {signal_fingerprint})",
                }

            # ---- Re-entry rule (Minervini/Schwager): max 2 re-entries per name within 30 days ----
            cur.execute(
                """
                SELECT COUNT(*) FROM algo_trades
                WHERE symbol = %s AND status IN (%s, %s)
                  AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
                """,
                (symbol, TradeStatus.OPEN.value, TradeStatus.PENDING.value),
            )
            result = cur.fetchone()
            pending_count = result[0] if result else 0
            if pending_count > 0:
                return {
                    "success": False,
                    "trade_id": "",
                    "status": "pending_trade_exists",
                    "message": f"{symbol}: {pending_count} pending/open trade(s) exist. Close before re-entering.",
                }

            # Find most recent CLOSED trade for this symbol in the last 30 days
            cur.execute(
                """
                SELECT trade_id, exit_date, exit_reason, profit_loss_pct,
                       COALESCE(reentry_count, 0) AS reentry_count
                FROM algo_trades
                WHERE symbol = %s AND status = %s
                  AND exit_date >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY exit_date DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                (symbol, TradeStatus.CLOSED.value),
            )
            prior = cur.fetchone()
            reentry_count = 0
            prior_trade_id = None
            if prior:
                prior_trade_id, exit_date, exit_reason, _exit_pnl, prior_reentry = prior
                # If prior trade was a stop-out, we're attempting a re-entry
                if exit_reason and (
                    "STOP" in (exit_reason or "").upper()
                    or "TIME" in (exit_reason or "").upper()
                ):
                    max_reentries = int(self.config.get("max_reentries_per_name", 2))
                    prior_reentry_count = int(prior_reentry)
                    if prior_reentry_count >= max_reentries:
                        return {
                            "success": False,
                            "trade_id": "",
                            "status": "reentry_blocked",
                            "reentry_blocked": True,
                            "message": f"{symbol}: {prior_reentry_count} prior re-entries within 30 days >= {max_reentries} max",
                        }
                    # NEW: Enforce minimum days between stop-out and re-entry (reset period for failed setup)
                    min_days_wait = int(
                        self.config.get("min_days_before_reentry_same_symbol", 5)
                    )
                    if exit_date:
                        from datetime import date as _date

                        exit_d = (
                            exit_date
                            if isinstance(exit_date, _date)
                            else exit_date.date()
                        )
                        days_since_exit = (
                            datetime.now(timezone.utc).date() - exit_d
                        ).days
                        if days_since_exit < min_days_wait:
                            return {
                                "success": False,
                                "trade_id": "",
                                "status": "reentry_cooldown",
                                "message": f"{symbol}: only {days_since_exit}d since stop-out; require {min_days_wait}d before re-entry (reset period)",
                            }
                    reentry_count = prior_reentry_count + 1

            execution_mode = self.config.get("execution_mode", "paper")
            trade_id = f"TRD-{uuid.uuid4().hex[:10].upper()}"
            rejection_reason = None  # Initialize for all code paths

            if execution_mode in ("paper", "dry"):
                logger.info(
                    f"[ENTRY] {symbol}: {execution_mode.upper()} mode - creating LOCAL order {trade_id}"
                )
                logger.warning(
                    f"[ENTRY] {symbol}: NOT TRADING LIVE - execution_mode is {execution_mode} (not 'auto')"
                )
                alpaca_order_id = f"LOCAL-{trade_id}"
                order_status = (
                    "open"  # P4: Changed from 'filled' to standardized 'open'
                )
                executed_price = entry_price
            elif execution_mode == "review":
                logger.info(
                    f"[ENTRY] {symbol}: REVIEW mode - creating PENDING order {trade_id}"
                )
                alpaca_order_id = f"PENDING-{trade_id}"
                order_status = "pending"  # P4: Standardized status
                executed_price = entry_price
            else:  # 'auto' — actually send to Alpaca as BRACKET ORDER
                logger.info(
                    f"[ENTRY] {symbol}: AUTO mode - SENDING LIVE ORDER TO ALPACA"
                )
                logger.info(
                    f"[ENTRY] {symbol}: Using Alpaca endpoint: {self.alpaca_base_url}"
                )
                self._order_send_time = time.time()  # Track for execution latency (TCA)
                order_result = self._send_alpaca_order(
                    symbol,
                    shares,
                    entry_price,
                    stop_loss_price=stop_loss_price,
                    take_profit_price=target_1_price,  # T1 as take-profit leg
                    order_class="bracket",
                )
                if not order_result["success"]:
                    # Alert on Alpaca API failure (non-blocking)
                    try:
                        from algo.reporting import AlertManager

                        AlertManager().send_position_alert(
                            symbol,
                            "EXECUTION_FAILURE",
                            "CRITICAL",
                            f'Order submission failed: {order_result.get("message", "Unknown error")}',
                        )
                    except NotificationError as alert_e:
                        logger.warning(f"Failed to send execution failure alert (non-blocking): {alert_e}")
                    return {
                        "success": False,
                        "trade_id": trade_id,
                        "status": "failed",
                        "message": order_result.get("message", "Order failed"),
                    }
                alpaca_order_id = order_result.get("order_id")
                if not alpaca_order_id:
                    return {
                        "success": False,
                        "trade_id": trade_id,
                        "status": "failed",
                        "message": "Alpaca response missing order_id",
                    }
                order_status = order_result.get("status", "pending")
                # Capture rejection reason if order was rejected
                rejection_reason = None
                if order_status == "rejected":
                    rejection_reason = (
                        order_result.get("rejection_reason")
                        or "Order rejected by Alpaca (no reason provided)"
                    )
                # For pending orders, executed_price is None (order not yet filled).
                # Use entry_price as the initial DB value; reconciliation updates it to
                # the actual fill price when the order executes. Slippage is computed at
                # reconciliation time, not here, so this doesn't corrupt fill data.
                executed_price = order_result.get("executed_price") or entry_price

                # Verify bracket legs were created successfully — FAIL-CLOSED if missing stop leg
                legs = order_result.get("legs", [])
                if order_result.get("order_class") == "bracket" and len(legs) < 2:
                    # Bracket order MUST have stop loss leg — cancel and reject if missing
                    try:
                        self._cancel_bracket_orders(alpaca_order_id)
                    except Exception as e:
                        logger.warning(
                            f"Failed to cancel bracket order {alpaca_order_id}: {e}"
                        )
                    return {
                        "success": False,
                        "trade_id": trade_id,
                        "status": "failed",
                        "message": f"Bracket order {alpaca_order_id} missing stop loss leg ({len(legs)} legs) — order cancelled and rejected",
                    }

                if order_status not in ("filled", "partially_filled"):
                    # Order pending, rejected, or cancelled — don't create position yet
                    if order_status in ("rejected", "cancelled", "expired"):
                        # B7: Alert on order rejection (non-blocking)
                        try:
                            notify(
                                "critical",
                                title=f"Order {order_status.upper()}: {symbol}",
                                message=f"Trade {trade_id}: {shares}sh @ ${entry_price:.2f} (stop ${stop_loss_price:.2f}) — {order_status}",
                            )
                        except NotificationError as alert_e:
                            logger.warning(f"Failed to send rejection alert (non-blocking): {alert_e}")
                        # Alpaca rejected the order
                        return {
                            "success": False,
                            "trade_id": trade_id,
                            "status": order_status,
                            "message": f"Alpaca {order_status} order: {symbol}",
                        }
                    # For pending orders, still create the trade record but mark as pending
                    # Position will be created when/if order fills (via reconciliation)

            # If fill price differs from signal price (slippage), recalculate targets based on actual fill
            if executed_price and executed_price != entry_price:
                slippage_pct = float(((Decimal(str(executed_price)) - Decimal(str(entry_price))) / Decimal(str(entry_price)) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                logger.info(
                    _redact_for_logs(
                        f"Slippage detected: {slippage_pct:+.2f}% (signal ${entry_price:.2f} → fill ${executed_price:.2f})"
                    )
                )
                # Recalculate targets from actual fill price
                actual_risk_per_share = Decimal(str(executed_price)) - Decimal(str(stop_loss_price))
                if actual_risk_per_share > 0:
                    t1_r = float(self.config.get("t1_target_r_multiple", 1.5))
                    t2_r = float(self.config.get("t2_target_r_multiple", 3.0))
                    t3_r = float(self.config.get("t3_target_r_multiple", 4.0))
                    target_1_price = float((Decimal(str(executed_price)) + (actual_risk_per_share * Decimal(str(t1_r)))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                    target_2_price = float((Decimal(str(executed_price)) + (actual_risk_per_share * Decimal(str(t2_r)))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                    target_3_price = float((Decimal(str(executed_price)) + (actual_risk_per_share * Decimal(str(t3_r)))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            # Compute initial position size pct using live or snapshot portfolio value
            _pv_for_pct = self._get_portfolio_value()
            if _pv_for_pct is None:
                logger.warning(
                    "Portfolio value unavailable for position size pct calculation"
                )
                position_size_pct = None
            else:
                # For pending orders, executed_price is None; use entry_price as estimate for pct calculation only
                price_for_pct = executed_price if executed_price else entry_price
                position_size_pct = (
                    float((Decimal(shares) * Decimal(str(price_for_pct)) / Decimal(str(_pv_for_pct)) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                    if _pv_for_pct > 0
                    else 0
                )

            # Build comprehensive entry reason
            entry_reason_parts = ["Algo signal — all tiers passed"]
            if swing_grade:
                entry_reason_parts.append(f"swing_grade={swing_grade}")
            if base_type:
                entry_reason_parts.append(f"base={base_type}")
            if stage_phase:
                entry_reason_parts.append(f"phase={stage_phase}")
            if exposure_tier_at_entry:
                entry_reason_parts.append(f"exposure={exposure_tier_at_entry}")
            entry_reason = " | ".join(entry_reason_parts)

            # Insert with FULL reasoning and idempotency key
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
                    trade_id,
                    idempotency_key,
                    symbol,
                    signal_date,
                    entry_date,
                    executed_price,
                    shares,
                    entry_reason,
                    stop_loss_price,
                    stop_method or "minervini_break_or_swing_low",
                    target_1_price,
                    float(self.config.get("t1_target_r_multiple", 1.5)),
                    target_2_price,
                    float(self.config.get("t2_target_r_multiple", 3.0)),
                    target_3_price,
                    float(self.config.get("t3_target_r_multiple", 4.0)),
                    order_status,
                    execution_mode,
                    alpaca_order_id,
                    position_size_pct,
                    int(sqs) if sqs is not None else None,
                    int(trend_score) if trend_score is not None else None,
                    swing_score,
                    swing_grade,
                    base_type,
                    base_quality,
                    STAGE_PHASE_MAPPING.get(stage_phase) if stage_phase else None,
                    stage_phase,
                    sector,
                    industry,
                    rs_percentile,
                    market_exposure_at_entry,
                    exposure_tier_at_entry,
                    stop_method,
                    stop_reasoning,
                    json.dumps(swing_components) if swing_components else None,
                    json.dumps(advanced_components) if advanced_components else None,
                    execution_mode == "auto",  # bracket_order = True only in auto mode
                    reentry_count,
                    prior_trade_id,
                    rejection_reason,
                ),
            )

            if order_status == "filled" or (
                order_status == "partially_filled" and execution_mode == "auto"
            ):
                # In auto mode, re-query order status to catch race where it was cancelled
                if execution_mode == "auto" and alpaca_order_id:
                    verified_status = self._verify_order_status(alpaca_order_id)
                    if verified_status not in ("filled", "partially_filled"):
                        return {
                            "success": False,
                            "trade_id": trade_id,
                            "status": verified_status or "unknown",
                            "message": f"Order status changed from {order_status} to {verified_status} — position not created",
                        }
                    order_status = verified_status

                position_id = f"POS-{trade_id}"
                # For partial fills, get actual filled quantity from Alpaca
                actual_shares = shares
                if order_status == "partially_filled" and alpaca_order_id:
                    filled_qty = self._get_order_filled_quantity(alpaca_order_id)
                    if filled_qty and filled_qty > 0:
                        actual_shares = filled_qty
                        logger.info(
                            _redact_for_logs(
                                f"Partial fill detected: {actual_shares} of {shares} shares filled"
                            )
                        )

                # B3: Defensive check for position value (ensure Decimal precision)
                position_value = float(Decimal(str(actual_shares)) * Decimal(str(executed_price)))
                if position_value <= 0:
                    return {
                        "success": False,
                        "trade_id": trade_id,
                        "status": "invalid",
                        "message": f"Invalid position value: {actual_shares} shares @ ${executed_price:.2f} = ${position_value:.2f}",
                    }
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
                        position_id,
                        symbol,
                        actual_shares,
                        executed_price,
                        executed_price,
                        position_value,
                        [trade_id],
                        stop_loss_price,
                        stop_loss_price,
                    ),
                )

            # Phase 3.2: Record execution quality (TCA) for every fill
            if order_status == "filled" or (
                order_status == "partially_filled" and execution_mode == "auto"
            ):
                try:
                    execution_latency_ms = int(
                        (time.time() - getattr(self, "_order_send_time", time.time()))
                        * 1000
                    )
                    tca_result = self.tca.record_fill(
                        trade_id=trade_id,
                        symbol=symbol,
                        signal_price=entry_price,
                        fill_price=executed_price,
                        shares_requested=shares,
                        shares_filled=actual_shares,
                        side="BUY",
                        execution_latency_ms=execution_latency_ms,
                    )
                    # Alert if slippage excessive (non-blocking)
                    if "alert" in tca_result:
                        try:
                            alert_data = tca_result["alert"]
                            notify(
                                alert_data["severity"].lower(),
                                title=f"TCA Alert: {alert_data['severity']}",
                                message=alert_data["message"],
                            )
                        except NotificationError as alert_e:
                            logger.warning(f"Failed to send TCA alert (non-blocking): {alert_e}")
                except (DatabaseError, Exception) as tca_e:
                    logger.warning(f"TCA recording failed: {type(tca_e).__name__}: {tca_e} (non-blocking)")

            # Send trade entry notification (non-blocking)
            try:
                notif_service = TradeNotificationService()
                notif_service._send_notification(
                    subject=f"ENTRY: {symbol}",
                    message=f"{shares:.2f} sh {symbol} @ ${(executed_price or entry_price):.2f} (stop ${stop_loss_price:.2f})",
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
            except NotificationError as notif_e:
                logger.warning(f"Failed to send entry notification (non-blocking): {notif_e}")

            return {
                "success": True,
                "trade_id": trade_id,
                "alpaca_order_id": alpaca_order_id,
                "status": order_status,
                "message": f"{shares} sh {symbol} @ ${(executed_price or entry_price):.2f} (stop ${stop_loss_price:.2f})",
            }

        try:
            return self._with_cursor(_execute_entry) or {
                "success": False,
                "trade_id": "",
                "status": "error",
                "message": "Unknown error",
            }
        except DuplicatePositionError as e:
            logger.error(f"Trade blocked (duplicate/idempotency): {e}")
            return {
                "success": False,
                "trade_id": "",
                "status": "duplicate",
                "message": str(e),
                "duplicate": True,
            }
        except PretradeCheckFailedError as e:
            logger.error(f"Pre-trade checks failed: {e}")
            return {
                "success": False,
                "trade_id": "",
                "status": "pretrade_check_failed",
                "message": str(e),
            }
        except PortfolioValueError as e:
            logger.critical(f"Portfolio value unavailable, trade rejected: {e}")
            return {
                "success": False,
                "trade_id": "",
                "status": "portfolio_value_unavailable",
                "message": str(e),
            }
        except OrderRejectedError as e:
            logger.error(f"Order rejected by Alpaca: {e}")
            return {
                "success": False,
                "trade_id": "",
                "status": "order_rejected",
                "message": str(e),
            }
        except OrderExecutionError as e:
            logger.error(f"Order execution failed: {e}")
            return {
                "success": False,
                "trade_id": "",
                "status": "order_failed",
                "message": str(e),
            }
        except DatabaseError as e:
            logger.critical(f"Database error during trade execution (order orphan risk): {e}")
            return {
                "success": False,
                "trade_id": "",
                "status": "database_error",
                "message": f"Database operation failed: {e}",
            }
        except TradingError as e:
            logger.error(f"Trading error: {type(e).__name__}: {e}")
            return {
                "success": False,
                "trade_id": "",
                "status": "trading_error",
                "message": str(e),
            }
        except Exception as e:
            logger.exception(f"Unexpected error during trade execution: {type(e).__name__}: {e}")
            return {
                "success": False,
                "trade_id": "",
                "status": "error",
                "message": f"Unexpected error: {type(e).__name__}",
            }

    # ---------- Exit (full or partial) ----------

    def _update_position_with_retry(
        self,
        cur,
        position_id: int,
        new_qty: float,
        new_stop_price: float | None = None,
        full_exit: bool = False,
        exit_stage: str | None = None,
    ) -> tuple:
        """Update position with retry logic for race condition safety.

        Handles concurrent updates by re-reading position before each retry.
        Returns: (success: bool, message: str or None)
        """
        def do_update():
            cur.execute(
                "SELECT quantity, current_stop_price FROM algo_positions WHERE position_id = %s",
                (position_id,),
            )
            result = cur.fetchone()
            if not result:
                raise ValueError(f"Position {position_id} not found")

            current_qty = result[0]
            current_stop = float(result[1]) if result[1] else 0

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
                increment_targets = (
                    1 if (exit_stage and "target" in exit_stage.lower()) else 0
                )
                update_sql = """UPDATE algo_positions
                               SET quantity = %s,
                                   position_value = %s * current_price,
                                   target_levels_hit = COALESCE(target_levels_hit, 0) + %s,
                                   current_stop_price = %s"""
                params = [new_qty, new_qty, increment_targets, effective_stop]

                if exit_stage == "target_1":
                    update_sql += ", target_1_hit_time = CURRENT_TIMESTAMP"
                elif exit_stage == "target_2":
                    update_sql += ", target_2_hit_time = CURRENT_TIMESTAMP"
                elif exit_stage == "target_3":
                    update_sql += ", target_3_hit_time = CURRENT_TIMESTAMP"

                update_sql += " WHERE position_id = %s AND quantity = %s"
                params.extend([position_id, current_qty])

                cur.execute(update_sql, params)

            return cur.rowcount > 0

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

    def exit_trade(
        self,
        trade_id: int,
        exit_price: float | None,
        exit_reason: str,
        exit_fraction: float = 1.0,
        exit_stage: str | None = None,
        new_stop_price: float | None = None,
        cur: Any | None = None,
    ) -> dict[str, Any]:
        """Exit all or part of a position.

        Args:
            trade_id: trade to exit
            exit_price: execution price for the exit (must be > 0; None when exit_fraction=0)
            exit_reason: reason text (logged in algo_trades + algo_audit_log)
            exit_fraction: 0 = stop-raise-only (no exit order); 0 < f <= 1 for partial/full exits
            exit_stage: optional 'target_1' | 'target_2' | 'target_3' | 'stop' | 'time' | 'distribution'
            new_stop_price: if provided, raise the stop on the residual shares (trailing stop)
            cur: Optional existing cursor (for transactional batching). If None, opens own context.

        Returns: { success, trade_id, shares_exited, profit_loss_dollars, profit_loss_pct, message }

        IMPORTANT: Transaction Safety
        - If cur is provided, operation is part of parent transaction (exit_engine.py flow)
        - If cur is None, operation opens its own transaction (backward compatibility)
        - All database writes are atomic within a single transaction
        """
        if exit_fraction == 0:
            if new_stop_price is None:
                return {
                    "success": False,
                    "message": "stop-raise-only (fraction=0) requires new_stop_price",
                }

            def _raise_stop(cursor):
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
                    return _raise_stop(cur) or {
                        "success": False,
                        "message": "Stop raise failed",
                    }
                else:
                    return self._with_cursor(_raise_stop) or {
                        "success": False,
                        "message": "Stop raise failed",
                    }
            except DatabaseError as e:
                logger.error(f"Database error raising stop: {e}")
                return {"success": False, "message": f"Database error: {e}"}
            except Exception as e:
                logger.error(f"Unexpected error raising stop: {type(e).__name__}: {e}")
                return {"success": False, "message": f"Stop raise failed: {e}"}

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

        def _execute_exit(cur):
            cur.execute(
                """SELECT status FROM algo_trades WHERE trade_id = %s""",
                (trade_id,),
            )
            trade_status_row = cur.fetchone()
            if trade_status_row and trade_status_row[0] == "closed":
                return {
                    "success": False,
                    "message": f"Trade {trade_id} is already closed (idempotency guard)",
                    "duplicate": True,
                }

            cur.execute(
                """SELECT t.symbol, t.entry_price, t.entry_quantity, t.stop_loss_price,
                       t.alpaca_order_id,
                       p.position_id, p.quantity, p.target_levels_hit, p.status
                FROM algo_trades t
                LEFT JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)
                WHERE t.trade_id = %s""",
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
                target_hits,
                position_status,
            ) = row

            entry_price = float(entry_price)
            entry_qty = int(entry_qty)
            stop_loss_price = float(stop_loss_price)
            current_qty = int(current_qty) if current_qty else 0
            target_hits = int(target_hits) if target_hits else 0

            if position_status == "closed":
                return {
                    "success": False,
                    "message": "Position already closed (idempotency guard)",
                    "duplicate": True,
                }

            if current_qty <= 0 and not position_id:
                return {"success": False, "message": f"No open position for {trade_id}"}

            current_qty_dec = Decimal(str(current_qty))
            exit_frac_dec = Decimal(str(exit_fraction))
            shares_to_exit_dec = (current_qty_dec * exit_frac_dec).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            shares_to_exit_dec = max(Decimal("0.01"), shares_to_exit_dec)
            shares_to_exit_dec = min(shares_to_exit_dec, current_qty_dec)
            shares_to_exit = float(shares_to_exit_dec)
            full_exit = shares_to_exit >= current_qty

            if full_exit and alpaca_order_id:
                cancel_result = self._cancel_bracket_orders(alpaca_order_id)
                if not cancel_result.get("success"):
                    logger.warning(
                        f"Failed to cancel bracket for {trade_id}: {cancel_result['message']}"
                    )

            execution_mode = self.config.get("execution_mode", "paper")
            actual_fill_price = None
            exit_order_result = {"success": False, "message": "No order sent"}
            is_estimated_price = True

            if execution_mode == "auto":
                exit_order_result = self._send_alpaca_exit(symbol, shares_to_exit)
                if exit_order_result.get("success"):
                    actual_fill_price = exit_order_result.get("filled_price")
                    is_estimated_price = False
                else:
                    try:
                        notify(
                            "critical",
                            title=f"EXIT ORDER FAILED: {symbol}",
                            message=f'Trade {trade_id}: Failed to exit {shares_to_exit}sh. {exit_order_result.get("message")}',
                        )
                    except NotificationError as e:
                        logger.warning(f"Failed to send exit failure alert (non-blocking): {e}")
                    return {
                        "success": False,
                        "message": f'Exit order failed: {exit_order_result.get("message")}',
                    }

            final_exit_price = actual_fill_price if actual_fill_price else exit_price

            if final_exit_price <= 0:
                logger.warning(f"Invalid exit price {final_exit_price} for {symbol}")
                return {
                    "success": False,
                    "message": f"Invalid exit price for {trade_id}",
                }
            if entry_price <= 0:
                logger.warning(f"Invalid entry price {entry_price} for {symbol}")
                return {
                    "success": False,
                    "message": f"Invalid entry price for {trade_id}",
                }

            risk_per_share = Decimal(str(entry_price)) - Decimal(str(stop_loss_price))
            r_multiple = (
                float(((Decimal(str(final_exit_price)) - Decimal(str(entry_price))) / risk_per_share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                if risk_per_share > 0
                else 0
            )
            pnl_per_share = Decimal(str(final_exit_price)) - Decimal(str(entry_price))
            pnl_dollars = float((pnl_per_share * Decimal(str(shares_to_exit))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            pnl_pct = float((pnl_per_share / Decimal(str(entry_price)) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) if entry_price > 0 else 0

            if not isinstance(pnl_dollars, (int, float)) or pnl_dollars != pnl_dollars:
                pnl_dollars = 0.0
            if not isinstance(pnl_pct, (int, float)) or pnl_pct != pnl_pct:
                pnl_pct = 0.0

            if full_exit:
                # If this is an estimated price, store it in estimated_exit_price for Phase 7 reconciliation
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

            current_qty_dec = Decimal(str(current_qty))
            shares_exited_dec = Decimal(str(shares_to_exit))
            new_qty_dec = current_qty_dec - shares_exited_dec
            new_qty = float(new_qty_dec)

            effective_stop = (
                new_stop_price if new_stop_price is not None else stop_loss_price
            )
            update_success, update_error = self._update_position_with_retry(
                cur=cur,
                position_id=position_id,
                new_qty=new_qty,
                new_stop_price=effective_stop,
                full_exit=full_exit or new_qty <= 0,
                exit_stage=exit_stage,
            )

            if not update_success:
                return {
                    "success": False,
                    "message": update_error or "Position update failed",
                }

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
            except (DatabaseError, Exception) as audit_e:
                logger.critical(
                    f"[AUDIT_FAILURE] Could not audit log trade exit {trade_id}: {type(audit_e).__name__}: {audit_e}"
                )
                raise AuditLogError(f"Failed to log trade exit: {audit_e}") from audit_e

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
                logger.warning(f"Failed to send exit notification (non-blocking): {notif_e}")

            return {
                "success": True,
                "trade_id": trade_id,
                "shares_exited": shares_to_exit,
                "profit_loss_dollars": pnl_dollars,
                "profit_loss_pct": pnl_pct,
                "r_multiple": r_multiple,
                "full_exit": full_exit,
                "message": (
                    f"Exited {shares_to_exit}sh of {symbol} @ ${final_exit_price:.2f} "
                    f"({pnl_pct:+.2f}%, {r_multiple:+.2f}R)"
                ),
            }

        try:
            if cur is not None:
                return _execute_exit(cur) or {
                    "success": False,
                    "trade_id": "",
                    "status": "error",
                    "message": "Unknown error",
                }
            else:
                return self._with_cursor(_execute_exit) or {
                    "success": False,
                    "trade_id": "",
                    "status": "error",
                    "message": "Unknown error",
                }
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
            return {"success": False, "message": f"Unexpected error: {type(e).__name__}"}
