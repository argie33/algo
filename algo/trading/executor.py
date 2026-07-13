#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from datetime import date as _date
from decimal import Decimal
from typing import Any

import psycopg2
import requests

from algo.infrastructure.config import AlgoConfig
from algo.reporting import TradeNotificationService, notify
from algo.trading.check_handler_strategies import CheckHandlerRegistry
from algo.trading.exceptions import (
    DatabaseError,
    DataUnavailableError,
    DuplicatePositionError,
    ExchangeAPIError,
    NotificationError,
    OrderExecutionError,
    OrderRejectedError,
    PortfolioValueError,
    PretradeCheckFailedError,
    TradingError,
)
from algo.trading.executor_entry_handler import EntryHandler
from algo.trading.executor_exit_handler import ExitHandler
from algo.trading.executor_strategies import create_execution_mode_strategy
from algo.trading.handler_context import HandlerContext
from algo.trading.notification_dispatcher import NotificationDispatcher
from algo.trading.order_manager import OrderManager
from algo.trading.position_tracker import PositionTracker
from algo.trading.trade_context import TradeContext
from config.credential_manager import get_alpaca_credentials
from utils.db import DatabaseContext
from utils.db.advisory_locks import (
    ALGO_POSITIONS_LOCK_ID,
    ALGO_TRADES_LOCK_ID,
    acquire_advisory_lock,
    release_advisory_lock,
)
from utils.db.retry import OptimisticLockRetry
from utils.trading.status import PositionStatus
from utils.validation import AlpacaResponseValidator

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

    # Mask prices: $123.45 '' $***
    message = re.sub(r"\$[\d.]+", "$***", message)
    # Mask shares: 100sh '' ***sh
    message = re.sub(r"(\d+)sh\b", "***sh", message)
    # Mask slippage: +1.23% '' +***%
    message = re.sub(r"([+-]\d+\.\d+)%", "***%", message)
    return message


class TradeExecutor:
    """Execute trades via Alpaca and track in database."""

    def __init__(self, config: AlgoConfig | dict[str, Any]) -> None:
        self.config = config

        # Get execution mode from config first (supports both dict and AlgoConfig objects)
        if "execution_mode" not in config or not config["execution_mode"]:
            raise ValueError(
                "CRITICAL: 'execution_mode' config missing or empty. "
                "Cannot proceed without explicit execution mode (paper/review/auto). "
                "Silently defaulting to paper would hide configuration errors. "
                "Check configuration and restart."
            )
        mode_str = str(config["execution_mode"]).lower()
        self.execution_mode_strategy = create_execution_mode_strategy(mode_str)
        self.execution_mode = mode_str

        # For paper trading mode, gracefully handle missing credentials
        self.alpaca_key = None
        self.alpaca_secret = None

        try:
            alpaca_creds = get_alpaca_credentials()
            self.alpaca_key = alpaca_creds.get("key")
            self.alpaca_secret = alpaca_creds.get("secret")
        except ValueError:
            # Credentials not found - if in paper mode, this is OK
            if self.execution_mode != "paper" and self.execution_mode != "auto":
                raise
            logger.warning("[EXECUTOR] Alpaca credentials not found - paper trading mode without live broker")

        # Use strategy pattern to resolve correct endpoint based on execution mode
        configured_url = os.getenv("APCA_API_BASE_URL")
        self.alpaca_base_url = self.execution_mode_strategy.resolve_base_url(configured_url)

        # For paper/auto mode, allow missing credentials (will not execute real trades)
        if self.execution_mode in ("paper", "auto"):
            if not self.alpaca_key or not self.alpaca_secret:
                logger.info("[EXECUTOR] Running in paper trading mode without live Alpaca credentials")
                self.alpaca_key = self.alpaca_key or "paper_trading_key"
                self.alpaca_secret = self.alpaca_secret or "paper_trading_secret"
        else:
            # Live mode requires actual credentials
            if not self.alpaca_key or not self.alpaca_secret or not self.alpaca_base_url:
                error_msg = (
                    f"[EXECUTOR_INIT_FAILED] Missing critical Alpaca credentials: "
                    f"key={'present' if self.alpaca_key else 'MISSING'} "
                    f"secret={'present' if self.alpaca_secret else 'MISSING'} "
                    f"url={'present' if self.alpaca_base_url else 'MISSING'}"
                )
                logger.critical(error_msg)
                raise ValueError(error_msg)

        # Validate initialization with execution mode strategy
        self.execution_mode_strategy.validate_and_log_initialization(
            self.alpaca_key, self.alpaca_secret, self.alpaca_base_url
        )

        # Wire TCA engine for execution quality tracking
        from algo.trading import TCAEngine

        self.tca = TCAEngine(config)

        # Wire pre-trade hard stops (Phase 5: independent risk layer)
        from algo.trading import PreTradeChecks

        self.pretrade = PreTradeChecks(config, self.alpaca_base_url, self.alpaca_key, self.alpaca_secret)

        # Wire trade validator for entry validation and duplicate detection
        from algo.trading.trade_validator import TradeValidator

        self.validator = TradeValidator(config, self.pretrade)

        # Validate R-multiple config values at init time (fail-fast) — must come before
        # handler initializations since EntryHandler and ExitHandler read these attributes
        required_r_multiples = [
            "t1_target_r_multiple",
            "t2_target_r_multiple",
            "t3_target_r_multiple",
        ]
        for r_key in required_r_multiples:
            if r_key not in config or config[r_key] is None:
                raise ValueError(
                    f"CRITICAL: '{r_key}' config missing or None. "
                    f"Cannot execute trades without explicit R-multiple configuration. "
                    f"Required: {required_r_multiples}"
                )
        self.t1_target_r_multiple = float(config["t1_target_r_multiple"])
        self.t2_target_r_multiple = float(config["t2_target_r_multiple"])
        self.t3_target_r_multiple = float(config["t3_target_r_multiple"])

        # Resolve Alpaca base URL using execution mode strategy
        self.alpaca_base_url = self.execution_mode_strategy.resolve_base_url(self.alpaca_base_url)
        self.is_paper = self.execution_mode_strategy.resolve_paper_mode()

        # Initialize position tracker specialist for all position DB operations
        self.position_tracker = PositionTracker(self.alpaca_key, self.alpaca_secret, self.alpaca_base_url)

        # Initialize notification dispatcher for trade notifications and TCA recording
        self.notification_dispatcher = NotificationDispatcher(config, self.tca)

        # Create handler context with dependencies (decouples handlers from direct executor access)
        handler_context = HandlerContext(
            config=config,
            validator=self.validator,
            tca=self.tca,
            t1_target_r_multiple=self.t1_target_r_multiple,
            t2_target_r_multiple=self.t2_target_r_multiple,
            t3_target_r_multiple=self.t3_target_r_multiple,
            execution_mode=self.execution_mode,
            get_portfolio_value_fn=self._get_portfolio_value,
            with_cursor_fn=self._with_cursor,
            validate_entry_conditions_fn=self._validate_entry_conditions,
            submit_and_validate_order_fn=self._submit_and_validate_order,
            cancel_bracket_orders_fn=self._cancel_bracket_orders,
            verify_order_status_fn=self._verify_order_status,
            get_order_filled_quantity_fn=self._get_order_filled_quantity,
            send_alpaca_exit_fn=self._send_alpaca_exit,
            update_position_with_retry_fn=self._update_position_with_retry,
        )

        # Initialize entry handler with context (not whole executor)
        self.entry_handler = EntryHandler(handler_context)

        # Initialize exit handler with context (not whole executor)
        self.exit_handler = ExitHandler(handler_context)

        # Initialize order manager specialist for order submission and validation
        self.order_manager = OrderManager(self.alpaca_key, self.alpaca_secret, self.alpaca_base_url)

        self.execution_mode_strategy.validate_and_log_initialization(
            self.alpaca_key, self.alpaca_secret, self.alpaca_base_url
        )

    def _setup_position_data(
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

    def _record_tca_and_notify(
        self,
        trade_id: str,
        symbol: str,
        entry_price: Decimal,
        executed_price: Decimal,
        shares: Decimal,
        actual_shares: Decimal,
        stop_loss_price: Decimal,
        target_1_price: Decimal | None,
        base_type: str | None,
        execution_mode: str,
    ) -> dict[str, Any]:
        """Record trade execution quality (TCA) and send notifications.

        Returns dict with any alerts that were generated.
        """
        tca_result = {}

        if execution_mode == "auto":
            if not hasattr(self, "_order_send_time"):
                raise RuntimeError(
                    f"[TCA CRITICAL] {symbol}: _order_send_time not set in AUTO mode. "
                    "Cannot record TCA without accurate send timestamp."
                )
            execution_latency_ms = int((time.time() - self._order_send_time) * 1000)
            if execution_latency_ms < 0:
                raise ValueError(
                    f"[TCA CRITICAL] {symbol}: negative latency {execution_latency_ms}ms. "
                    "Clock skew or time tracking error."
                )

            # CRITICAL: TCA (Trade Cost Analysis) recording is part of compliance audit trail.
            # Execution quality tracking must be recorded before confirming trade entry.
            # If TCA fails, the trade must NOT proceed — missing audit record = compliance gap.
            if not isinstance(trade_id, int):
                if not (isinstance(trade_id, str) and trade_id.isdigit()):
                    raise RuntimeError(
                        f"[TCA CRITICAL] {symbol}: Invalid trade_id '{trade_id}' (not int or digit string). "
                        "Trade ID must be a valid integer. Cannot record execution without valid trade ID."
                    )
                trade_id_int = int(trade_id)
            else:
                trade_id_int = trade_id

            try:
                tca_result = self.tca.record_fill(
                    trade_id=trade_id_int,
                    symbol=symbol,
                    signal_price=float(entry_price),
                    fill_price=float(executed_price),
                    shares_requested=int(shares),
                    shares_filled=int(actual_shares),
                    side="BUY",
                    execution_latency_ms=execution_latency_ms,
                )
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
            except DatabaseError as tca_e:
                msg = (
                    f"[TCA CRITICAL] {symbol}: Failed to record execution quality data: {tca_e}. "
                    f"TCA is part of compliance audit trail and cannot be skipped. "
                    f"Trade entry halted — cannot proceed without audit record. "
                    f"Check database connection and tca schema availability."
                )
                logger.critical(msg)
                raise RuntimeError(msg) from tca_e

        try:
            notif_service = TradeNotificationService(config={"enabled": True})
            # CRITICAL: Don't silently fall back to entry_price if execution price unknown
            if executed_price is None:
                logger.error(f"[EXECUTOR] Executed price missing for {symbol} - using entry price")
                entry_price_disp = entry_price
            else:
                entry_price_disp = executed_price
            notif_service._send_notification(
                subject=f"ENTRY: {symbol}",
                message=(f"{actual_shares:.2f} sh {symbol} @ ${entry_price_disp:.2f} (stop ${stop_loss_price:.2f})"),
                kind="trade_entry",
                severity="info",
                symbol=symbol,
                details={
                    "entry_price": executed_price,
                    "shares": float(actual_shares),
                    "stop_loss": stop_loss_price,
                    "target_1": target_1_price,
                    "base_type": base_type,
                    "trade_id": trade_id,
                },
            )
        except NotificationError as notif_e:
            raise RuntimeError(
                f"CRITICAL: Failed to send entry notification for {symbol} (trade {trade_id}): {notif_e}. "
                f"Trader was NOT notified of entry. Cannot proceed without notification confirmation."
            ) from notif_e

        return tca_result

    def _submit_and_validate_order(
        self,
        symbol: str,
        trade_id: str,
        shares: Decimal,
        entry_price: Decimal,
        stop_loss_price: Decimal,
        target_1_price: Decimal | None,
        execution_mode: str,
    ) -> tuple[bool, str, str, str, Decimal | None, str | None]:
        """Submit order via Alpaca or create placeholder for paper/review mode.

        Returns: (success, alpaca_order_id, order_status, error_message, executed_price, rejection_reason)
        """
        if execution_mode in ("paper", "dry"):
            logger.info(f"[ENTRY] {symbol}: {execution_mode.upper()} mode - creating LOCAL order {trade_id}")
            logger.warning(f"[ENTRY] {symbol}: NOT TRADING LIVE - execution_mode is {execution_mode} (not 'auto')")
            return (
                True,
                f"LOCAL-{trade_id}",
                "open",
                "",
                entry_price,
                None,
            )

        if execution_mode == "review":
            logger.info(f"[ENTRY] {symbol}: REVIEW mode - creating PENDING order {trade_id}")
            return (
                True,
                f"PENDING-{trade_id}",
                "pending",
                "",
                entry_price,
                None,
            )

        # Auto mode: send to Alpaca
        logger.info(f"[ENTRY] {symbol}: AUTO mode - SENDING LIVE ORDER TO ALPACA")
        logger.info(f"[ENTRY] {symbol}: Using Alpaca endpoint: {self.alpaca_base_url}")
        self._order_send_time = time.time()

        try:
            # Use OrderManager specialist to submit bracket order
            order_result = self.order_manager.send_bracket_order(
                symbol=symbol,
                shares=float(shares),
                entry_price=float(entry_price),
                stop_loss_price=float(stop_loss_price),
                take_profit_price=float(target_1_price) if target_1_price else None,
            )

            # FAIL-FAST: Validate response schema before using (contract enforcement)
            if "success" not in order_result:
                raise OrderExecutionError(
                    f"[ENTRY] {symbol}: OrderManager returned malformed response (missing 'success' field). "
                    f"Contract violation. Available keys: {list(order_result.keys())}"
                )
            if not order_result["success"]:
                error_msg = order_result.get("message")
                if not error_msg:
                    raise OrderExecutionError(
                        f"[ENTRY] {symbol}: Order rejected but no error message provided. "
                        f"OrderManager must return 'message' field on failure."
                    )
                logger.error(f"[ENTRY] {symbol}: Order rejected - {error_msg}")
                return (
                    False,
                    trade_id,
                    "",
                    error_msg,
                    None,
                    order_result.get("rejection_reason"),
                )

            # Extract order details — all required when success=True
            alpaca_order_id = order_result.get("order_id")
            if not alpaca_order_id:
                raise OrderExecutionError(
                    f"[ENTRY] {symbol}: OrderManager returned success=True but no order_id. "
                    f"Cannot proceed without order ID. OrderManager contract violated."
                )

            order_status = order_result.get("status")
            if not order_status:
                raise OrderExecutionError(
                    f"[ENTRY] {symbol}: OrderManager returned success=True but no status. "
                    f"Cannot track order without status. OrderManager contract violated."
                )

            executed_price = order_result["executed_price"] if "executed_price" in order_result else None
            if executed_price is None:
                raise OrderExecutionError(
                    f"[ENTRY] {symbol}: OrderManager returned success=True but no executed_price. "
                    f"Cannot record trade without execution price. OrderManager contract violated."
                )

            logger.info(
                f"[ENTRY] {symbol}: Order {alpaca_order_id} submitted successfully - "
                f"status={order_status}, executed_price=${executed_price}"
            )

            # FAIL-FAST: executed_price is guaranteed by validation above (line 423)
            # No fallback to entry_price — use captured execution price directly
            return (
                True,
                alpaca_order_id,
                order_status,
                "",
                Decimal(str(executed_price)),
                None,
            )

        except OrderExecutionError as e:
            # Order submission contract violation or rejection (non-retryable)
            logger.error(f"[ENTRY] {symbol}: Order execution error (contract violation): {e}")
            return (
                False,
                trade_id,
                "",
                f"Order submission error: {str(e)[:100]}",
                None,
                None,
            )
        except ExchangeAPIError as e:
            # Transient API error (potentially retryable)
            logger.warning(f"[ENTRY] {symbol}: Transient API error during order submission: {e}")
            return (
                False,
                trade_id,
                "",
                f"API error (may retry): {str(e)[:100]}",
                None,
                None,
            )
        except Exception as e:
            # Unexpected error - log fully for debugging
            logger.exception(f"[ENTRY] {symbol}: Unexpected exception during order submission: {type(e).__name__}: {e}")
            return (
                False,
                trade_id,
                "",
                f"Unexpected error: {str(e)[:100]}",
                None,
                None,
            )

    def _validate_entry_conditions(
        self,
        cur: Any,
        symbol: str,
        signal_date: _date,
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Validate all entry conditions in a single consolidated check.

        Returns: (is_valid, error_message, error_details_dict_or_none)
        """
        checks: list[tuple[Callable[..., Any], tuple[Any, ...], str]] = [
            (
                self.validator.check_idempotent_duplicate,
                (cur, symbol, signal_date, entry_price, stop_loss_price),
                "idempotent",
            ),
            (
                self.validator.check_open_position_in_symbol,
                (cur, symbol),
                "open_position",
            ),
            (
                self.validator.check_signal_fingerprint_duplicate,
                (cur, symbol, signal_date, entry_price, stop_loss_price),
                "fingerprint",
            ),
            (
                self.validator.check_pending_trades,
                (cur, symbol),
                "pending",
            ),
            (
                self.validator.check_reentry_rules,
                (cur, symbol),
                "reentry",
            ),
        ]

        for check_fn, args, check_name in checks:
            result = check_fn(*args)
            check_failed, error_msg, status_dict = self._process_validation_result(check_name, result)
            if check_failed:
                return check_failed, error_msg, status_dict

        return True, "", None

    def _process_validation_result(
        self, check_name: str, result: tuple[Any, ...]
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Process validation check result using strategy pattern.

        Delegates to handler that knows how to unpack each check type's result tuple.

        Args:
            check_name: Name of the validation check
            result: Tuple result from the check (structure varies by check_name)

        Returns:
            (should_return_early, error_msg, status_dict_or_none)
        """
        try:
            handler = CheckHandlerRegistry.get_handler(check_name)
            return handler.process(result)
        except ValueError as e:
            logger.error(f"[VALIDATION] Unknown check type: {check_name}: {e}")
            raise

    def _with_cursor(self, operation: Any, acquire_locks: bool = False) -> Any:
        """Execute an operation with a cursor via DatabaseContext.

        Args:
            operation: Callable that takes a cursor and returns a result
            acquire_locks: If True, acquire advisory locks for algo_trades and algo_positions
        """
        try:
            with DatabaseContext("write") as cur:
                if acquire_locks:
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

    def _get_portfolio_value(self) -> Decimal | None:
        from algo.trading import PositionSizer

        try:
            sizer = PositionSizer(self.config.to_dict() if hasattr(self.config, "to_dict") else self.config)
            pv = sizer.get_portfolio_value()
            return pv
        except PortfolioValueError as e:
            logger.error(f"Portfolio value unavailable (critical): {e}")
            raise PortfolioValueError(f"Cannot determine portfolio value: {e}") from e
        except (DatabaseError, ValueError) as e:
            logger.error(f"Failed to get portfolio value ({type(e).__name__}): {e}")
            raise DataUnavailableError(f"Portfolio value calculation failed: {e}") from e
        except (requests.RequestException, requests.Timeout) as e:
            logger.error(f"Alpaca API error getting portfolio value: {e}")
            raise DataUnavailableError(f"Cannot reach Alpaca: {e}") from e

    def _cancel_bracket_orders(self, alpaca_order_id: str) -> dict[str, Any]:
        return self.order_manager.cancel_bracket_orders(alpaca_order_id)

    def _verify_order_status(self, alpaca_order_id: str) -> str | None:
        return self.order_manager.verify_order_status(alpaca_order_id)

    def _get_order_filled_quantity(self, alpaca_order_id: str) -> float | None:
        return self.order_manager.get_order_filled_quantity(alpaca_order_id)

    def _send_alpaca_exit(self, symbol: str, shares: float) -> dict[str, Any]:
        return self.order_manager.send_market_exit(symbol, shares, self.execution_mode)

    # ---------- Entry ----------

    def execute_trade(
        self,
        symbol: str,
        entry_price: Decimal | float,
        shares: Decimal | float,
        stop_loss_price: Decimal | float,
        target_1_price: Decimal | float | None = None,
        target_2_price: Decimal | float | None = None,
        target_3_price: Decimal | float | None = None,
        signal_date: _date | None = None,
        entry_date: _date | None = None,
        sqs: Any | None = None,
        trend_score: float | None = None,
        composite_score: float | None = None,
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
        advanced_components: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a new entry trade by delegating to EntryHandler.

        Returns: {
            'success': bool,
            'trade_id': str,
            'alpaca_order_id': str,
            'status': str,
            'message': str,
            'duplicate': bool (only when blocked by idempotency)
        }
        """
        try:
            context = TradeContext.from_params(
                symbol=symbol,
                entry_price=entry_price,
                shares=shares,
                stop_loss_price=stop_loss_price,
                target_1_price=target_1_price,
                target_2_price=target_2_price,
                target_3_price=target_3_price,
                signal_date=signal_date,
                entry_date=entry_date,
                sqs=sqs,
                trend_score=trend_score,
                base_type=base_type,
                base_quality=base_quality,
                stage_phase=stage_phase,
                sector=sector,
                industry=industry,
                rs_percentile=rs_percentile,
                market_exposure_at_entry=market_exposure_at_entry,
                exposure_tier_at_entry=exposure_tier_at_entry,
                stop_method=stop_method,
                stop_reasoning=stop_reasoning,
                advanced_components=advanced_components,
            )
            return self.entry_handler.execute_entry(context)
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
        """Exit all or part of a position with guaranteed transaction atomicity.

        Delegates to ExitHandler for focused, testable exit execution logic.

        Args:
            trade_id: trade to exit
            exit_price: execution price for the exit (must be > 0; None when exit_fraction=0)
            exit_reason: reason text (logged in algo_trades + algo_audit_log)
            exit_fraction: 0 = stop-raise-only (no exit order); 0 < f <= 1 for partial/full exits
            exit_stage: optional 'target_1' | 'target_2' | 'target_3' | 'stop' | 'time' | 'distribution'
            new_stop_price: if provided, raise the stop on the residual shares (trailing stop)
            cur: Optional existing cursor (for transactional batching). If None, opens own context.

        Returns: { success, trade_id, shares_exited, profit_loss_dollars, profit_loss_pct, message }
        """
        return self.exit_handler.execute_exit(
            trade_id=trade_id,
            exit_price=exit_price,
            exit_reason=exit_reason,
            exit_fraction=exit_fraction,
            exit_stage=exit_stage,
            new_stop_price=new_stop_price,
            cur=cur,
        )
