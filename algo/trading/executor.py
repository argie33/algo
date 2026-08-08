#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Callable
from datetime import date as _date
from decimal import Decimal
from typing import Any

import psycopg2
import requests
from psycopg2.extensions import cursor as PsycopgCursor

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
from algo.trading.order_manager import OrderManager
from algo.trading.position_tracker import PositionTracker
from algo.trading.trade_context import TradeContext
from algo.config.credential_manager import get_alpaca_credentials
from utils.db import DatabaseContext
from utils.db.advisory_locks import (
    ALGO_POSITIONS_LOCK_ID,
    ALGO_TRADES_LOCK_ID,
    acquire_advisory_lock,
    release_advisory_lock,
)
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

        # CRITICAL: "auto" is this system's real live-trading mode (the only mode that
        # actually sends orders to Alpaca - see _submit_and_validate_order). The four checks
        # below originally grouped it with "paper", meaning a credential-fetch failure in
        # live trading either silently didn't re-raise (misleadingly logged as "paper trading
        # mode without live broker") or, worse, got backfilled with literal placeholder
        # strings ("paper_trading_key"/"paper_trading_secret") a few lines down instead of
        # failing loudly - live orders would then be attempted with garbage credentials and
        # fail deep inside the HTTP call with a confusing 401/403 instead of a clear
        # "credentials missing" error at startup. Same bug class, same fix, as
        # position_sizer.py's _fetch_live_alpaca_equity and executor_entry_handler.py's
        # order-rejection handling (both fixed earlier this session) - scope to paper only.
        try:
            alpaca_creds = get_alpaca_credentials()
            self.alpaca_key = alpaca_creds.get("key")
            self.alpaca_secret = alpaca_creds.get("secret")
        except ValueError as e:
            logger.debug(f"[EXECUTOR] Alpaca credentials not found (ValueError): {e}")
            if self.execution_mode != "paper":
                logger.critical(f"[EXECUTOR_INIT] Non-paper mode requires Alpaca credentials, but got ValueError: {e}")
                raise
            logger.warning("[EXECUTOR] Alpaca credentials not found - paper trading mode without live broker")
        except (TypeError, AttributeError, KeyError) as e:
            logger.error(
                f"[EXECUTOR] Failed to extract credentials from manager response: "
                f"{type(e).__name__}: {e}. Response structure may be invalid."
            )
            if self.execution_mode != "paper":
                raise ValueError(f"Credential manager returned invalid structure: {type(e).__name__}: {e}") from e
            logger.warning("[EXECUTOR] Credential structure invalid - paper trading mode without live broker")
        except Exception as e:
            logger.exception(f"[EXECUTOR] Unexpected error during credential retrieval: {type(e).__name__}: {e}")
            if self.execution_mode != "paper":
                raise
            logger.warning("[EXECUTOR] Credential retrieval failed - paper trading mode without live broker")

        # Use strategy pattern to resolve correct endpoint based on execution mode
        configured_url = os.getenv("APCA_API_BASE_URL")
        self.alpaca_base_url = self.execution_mode_strategy.resolve_base_url(configured_url)

        # For paper/dry mode only, allow missing credentials (will not execute real trades)
        # "paper" and "dry" are both LOCAL-only modes that never touch Alpaca
        # "review" and "auto" require actual credentials to submit orders
        # CRITICAL: Do NOT use placeholder credentials - they cause confusing errors downstream
        # and mask actual configuration problems. If credentials are missing, log clearly but leave None.
        if self.execution_mode in ("paper", "dry"):
            if not self.alpaca_key or not self.alpaca_secret:
                logger.warning(
                    f"[EXECUTOR] Running in {self.execution_mode} mode without live Alpaca credentials. "
                    "Reconciliation will use database state only (no live Alpaca API calls). "
                    "Credentials will remain None to avoid confusing error messages with fake values."
                )
        else:
            # review/auto modes require actual credentials
            if not self.alpaca_key or not self.alpaca_secret or not self.alpaca_base_url:
                error_msg = (
                    f"[EXECUTOR_INIT_FAILED] Missing critical Alpaca credentials for {self.execution_mode} mode: "
                    f"key={'present' if self.alpaca_key else 'MISSING'} "
                    f"secret={'present' if self.alpaca_secret else 'MISSING'} "
                    f"url={'present' if self.alpaca_base_url else 'MISSING'}"
                )
                logger.critical(error_msg)
                raise ValueError(error_msg)

            # CRITICAL: Verify execution mode wasn't silently downgraded to paper by safety guards
            # If execution_mode='auto' but safety checks force paper endpoint, raise error explicitly
            if self.execution_mode == "auto":
                if self.execution_mode_strategy.resolve_paper_mode():
                    raise ValueError(
                        "[EXECUTOR_INIT_FAILED] Auto mode requested but safety guards prevented execution. "
                        "Execution strategy downgraded to paper mode. "
                        "Check: ALGO_LIVE_TRADING='I_UNDERSTAND_REAL_MONEY', "
                        "ALPACA_PAPER_TRADING='false', APCA_API_BASE_URL (must point to live endpoint), "
                        "and API credentials must be present."
                    )

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
        from algo.trading.trade_validator import TradeValidator, _validate_and_load_r_multiples

        self.validator = TradeValidator(config, self.pretrade)

        # Validate and load R-multiple config (fail-fast, no defaults)
        self.t1_target_r_multiple, self.t2_target_r_multiple, self.t3_target_r_multiple = (
            _validate_and_load_r_multiples(config)
        )

        # Resolve Alpaca base URL using execution mode strategy
        self.alpaca_base_url = self.execution_mode_strategy.resolve_base_url(self.alpaca_base_url)
        self.is_paper = self.execution_mode_strategy.resolve_paper_mode()

        # Initialize position tracker specialist for all position DB operations
        self.position_tracker = PositionTracker(self.alpaca_key, self.alpaca_secret, self.alpaca_base_url)

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
            wait_for_order_fill_fn=self._wait_for_order_fill,
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
            # If TCA fails, the trade must NOT proceed - missing audit record = compliance gap.
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
                    f"Trade entry halted - cannot proceed without audit record. "
                    f"Check database connection and tca schema availability."
                )
                logger.critical(msg)
                raise RuntimeError(msg) from tca_e

        try:
            notif_service = TradeNotificationService(config={"enabled": True})
            if executed_price is None:
                raise ValueError(
                    f"[EXECUTOR] CRITICAL: Executed price missing for {symbol}. "
                    f"Cannot record trade without actual execution price (would silently use entry price {entry_price}). "
                    f"This is a data integrity failure - the order may have filled at a different price. "
                    f"Fail-fast: manual intervention required."
                )
            notif_service._send_notification(
                subject=f"ENTRY: {symbol}",
                message=(f"{actual_shares:.2f} sh {symbol} @ ${executed_price:.2f} (stop ${stop_loss_price:.2f})"),
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
        idempotency_key: str,
    ) -> tuple[bool, str, str, str, Decimal | None, str | None, dict[str, Any] | None]:
        """Submit order via Alpaca or create placeholder for paper/review mode.

        Returns: (success, alpaca_order_id, order_status, error_message, executed_price,
        rejection_reason, order_result) - order_result is the raw OrderManager response dict
        (carries "legs"/"order_class" for bracket-leg validation) on a successful auto-mode
        submission, None otherwise (paper/dry/review never call the broker; failure/exception
        paths have no bracket to validate).

        CRITICAL FIX: this used to stash the raw response as self._last_order_result and the
        send timestamp as self._order_send_time, expecting executor_entry_handler.py's
        EntryHandler to read them back via self.context._last_order_result/._order_send_time.
        But self here is TradeExecutor (this method is passed into HandlerContext as a bound
        method - see executor.py's HandlerContext construction - so `self` inside it stays
        bound to TradeExecutor no matter how it's invoked), while `self.context` in
        EntryHandler is a separate HandlerContext instance that never received either
        attribute. Confirmed live 2026-07-27: in execution_mode="auto" (the only mode that
        reaches this branch and the system's actual live-trading mode), every successful order
        submission hit an AttributeError on the very next line of entry processing - after Alpaca
        had already accepted a real order with real money - which rolled back the same DB
        transaction that would have recorded the trade/position, leaving a live, unrecorded
        position invisible to every downstream stop-loss/exit/circuit-breaker check. This
        codebase's paper-only local dev environment never exercises execution_mode="auto", which
        is why this was never caught. Returning the value explicitly instead of stashing it on
        an object the caller doesn't actually read from removes the whole cross-object footgun.
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
                # CRITICAL: use idempotency_key (deterministic hash of symbol/signal_date/
                # entry_price/stop_loss_price), NOT trade_id (a fresh random UUID minted on
                # every attempt - see executor_entry_handler.py). The whole point of a
                # client_order_id is that a genuine retry of the *same* underlying trade
                # intent (e.g. Phase 8 reprocessing today's signal after a crash/restart)
                # reuses the same value so Alpaca can reject it as a duplicate; a random
                # trade_id would be different on every attempt and defeat that protection.
                client_order_id=idempotency_key[:48],
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
                    None,
                )

            # Extract order details - all required when success=True
            alpaca_order_id = order_result.get("order_id")
            if not alpaca_order_id or not isinstance(alpaca_order_id, str) or not alpaca_order_id.strip():
                raise OrderExecutionError(
                    f"[ENTRY] {symbol}: OrderManager returned success=True but invalid order_id: {alpaca_order_id!r}. "
                    f"order_id must be a non-empty string. OrderManager contract violated."
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
            # No fallback to entry_price - use captured execution price directly
            return (
                True,
                alpaca_order_id,
                order_status,
                "",
                Decimal(str(executed_price)),
                None,
                order_result,
            )

        except OrderExecutionError as e:
            # Order submission contract violation or rejection (non-retryable)
            logger.error(f"[ENTRY] {symbol}: Order execution error (contract violation): {e}")
            return (
                False,
                trade_id,
                "",
                f"Order submission error: {str(e)[:500]}",
                None,
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
                f"API error (may retry): {str(e)[:500]}",
                None,
                None,
                None,
            )
        except Exception as e:
            # Unexpected error - log fully for debugging
            error_detail = f"{type(e).__name__}: {str(e)}"
            logger.exception(f"[ENTRY] {symbol}: Unexpected exception during order submission: {error_detail}")
            logger.error(f"[ENTRY] {symbol}: Full traceback and context above ^")
            return (
                False,
                trade_id,
                "",
                f"Unexpected error: {error_detail[:200]}",
                None,
                None,
                None,
            )

    def _validate_entry_conditions(
        self,
        cur: PsycopgCursor[Any],
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

        # CRITICAL FIX: check_reentry_rules() computes a real reentry_count (prior_reentry + 1
        # when the prior exit was a stop-out) specifically so max_reentries_per_name can cap
        # repeated re-entries into a name that keeps stopping the algo out. But
        # ReentryCheckHandler.process() only ever surfaces this value on the FAILURE path (via
        # status_dict) - on success it discards the check's 3rd tuple element entirely and this
        # function returned a bare `None` for error_details, so _insert_trade_record() had no
        # way to receive it and wrote a hardcoded literal 0 for every single trade. That made
        # max_reentries_per_name permanently inert: every re-entry read back reentry_count=0 the
        # next time, so `prior_reentry_count + 1 >= max_reentries_per_name` could only ever be
        # 1 >= max, never escalating past the first re-entry regardless of how many times a
        # symbol actually re-entered and stopped out again. Captured directly here, bypassing
        # the pass/fail handler abstraction (which has no concept of "successful check produced
        # a value the caller still needs"), and threaded through error_details on the success
        # path so the actual computed count reaches TradeInsertionRequest.
        reentry_count = 0
        for check_fn, args, check_name in checks:
            result = check_fn(*args)
            logger.debug(f"[VALIDATION LOOP] Check '{check_name}' returned: {result}")
            if check_name == "reentry" and len(result) > 2:
                reentry_count = result[2]
            check_failed, error_msg, status_dict = self._process_validation_result(check_name, result)
            logger.debug(
                f"[VALIDATION LOOP] Check '{check_name}' processed: check_failed={check_failed}, error_msg={error_msg}"
            )
            if check_failed:
                logger.warning(
                    f"[VALIDATION LOOP] Check '{check_name}' FAILED - returning early with error: {error_msg}"
                )
                # CRITICAL FIX: Return is_valid=False when a check fails (not check_failed which is True)
                return False, error_msg, status_dict
            logger.debug(f"[VALIDATION LOOP] Check '{check_name}' passed, continuing to next check")

        logger.debug("[VALIDATION LOOP] All checks passed!")
        return True, "", {"reentry_count": reentry_count}

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

    def _with_cursor(self, operation: Callable[[PsycopgCursor[Any]], Any], acquire_locks: bool = False) -> Any:
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
                        result = operation(cur)
                        logger.debug(f"[_with_cursor] Operation succeeded, returning result (locks still held)")
                        return result
                    except Exception as op_exc:
                        # CRITICAL FIX 2026-07-30: Transaction is now aborted after operation failure
                        # Cannot release locks on aborted transaction. Rollback explicitly first.
                        logger.debug(f"[_with_cursor] Operation raised exception: {type(op_exc).__name__}: {op_exc}")
                        try:
                            cur.execute("ROLLBACK")
                        except Exception as rollback_exc:
                            logger.debug(f"Rollback during exception handling failed: {rollback_exc}")
                        # Try to release locks, but tolerate failure (transaction was already rolled back)
                        try:
                            release_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                        except Exception as pos_lock_exc:
                            logger.debug(f"Could not release positions lock: {pos_lock_exc}")
                        try:
                            release_advisory_lock(cur, ALGO_TRADES_LOCK_ID, "algo_trades")
                        except Exception as trades_lock_exc:
                            logger.debug(f"Could not release trades lock: {trades_lock_exc}")
                        raise op_exc
                    finally:
                        # Release locks after successful operation
                        try:
                            release_advisory_lock(cur, ALGO_POSITIONS_LOCK_ID, "algo_positions")
                            release_advisory_lock(cur, ALGO_TRADES_LOCK_ID, "algo_trades")
                            logger.debug(f"[_with_cursor] Locks released successfully")
                        except Exception as lock_exc:
                            # Lock release failure on success path: log but DO NOT raise
                            # Raising here would cause DatabaseContext to rollback the already-succeeded transaction
                            # Resulting in: trade inserted to DB successfully, but then rolled back due to lock error
                            # Database ends up with nothing committed, despite operation succeeding
                            logger.warning(f"Failed to release locks after successful operation (non-fatal): {lock_exc}")
                else:
                    logger.debug(f"[_with_cursor] No locks requested, executing operation")
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

    def _wait_for_order_fill(
        self, symbol: str, alpaca_order_id: str, max_wait_seconds: int = 30
    ) -> tuple[bool, float | None, str]:
        """Wait for order to fill at broker before recording trade in DB.

        CRITICAL: Do not write to database until this confirms fill.
        """
        return self.order_manager.wait_for_order_fill(symbol, alpaca_order_id, max_wait_seconds)

    def _send_alpaca_exit(self, symbol: str, shares: float, trade_id: int) -> dict[str, Any]:
        # CRITICAL: id is persisted BEFORE calling Alpaca, in its own immediately-committed
        # transaction (_with_cursor opens a fresh DatabaseContext) independent of the caller's
        # still-open exit transaction - so it survives a crash between Alpaca confirming a fill
        # and that transaction committing. A retry after such a crash finds this same pending
        # value already set and reuses it instead of minting a new one, so Alpaca's own
        # client_order_id dedup protection (already relied on for entries - see
        # execute_trade's idempotency_key usage) covers this resubmission too, rather than
        # executing a genuinely separate duplicate sell order. Only cleared by
        # executor_exit_handler.py once the exit is confirmed and recorded - never on
        # failure/timeout, since an ambiguous outcome must keep the same id available for the
        # next retry to reuse. Stable across send_market_exit's own internal retry loop for
        # the same reason it always was. Distinct trade_id per call is what already prevents
        # a stable-forever key from blocking legitimate later partial exits on the same trade -
        # each exit attempt for the same trade still gets its own persisted id once the prior
        # one clears on success.
        def _get_or_set_pending_id(cur: PsycopgCursor[Any]) -> str:
            cur.execute(
                "SELECT pending_exit_client_order_id FROM algo_trades WHERE trade_id = %s",
                (trade_id,),
            )
            row = cur.fetchone()
            existing = row[0] if row else None
            if existing:
                logger.warning(
                    f"[EXIT] {symbol} trade {trade_id}: reusing pending client_order_id "
                    f"{existing} from an unresolved prior attempt (crash recovery)."
                )
                return str(existing)
            new_id = f"exit-{trade_id}-{uuid.uuid4().hex[:16]}"
            cur.execute(
                "UPDATE algo_trades SET pending_exit_client_order_id = %s WHERE trade_id = %s",
                (new_id, trade_id),
            )
            return new_id

        client_order_id = self._with_cursor(_get_or_set_pending_id)
        return self.order_manager.send_market_exit(symbol, shares, self.execution_mode, client_order_id)

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
                "message": f"Unexpected error: {type(e).__name__}: {str(e)[:200]}",
            }

    # ---------- Exit (full or partial) ----------

    def _update_position_with_retry(
        self,
        cur: PsycopgCursor[Any],
        position_id: int,
        new_qty: float,
        new_stop_price: float | None = None,
        full_exit: bool = False,
        exit_stage: str | None = None,
        pnl_dollars: float | None = None,
        pnl_pct: float | None = None,
        exit_reason: str | None = None,
    ) -> tuple[bool, str | None]:
        """Update position with retry logic for race condition safety.

        Delegates to self.position_tracker.update_position_with_retry(), which was
        already instantiated (self.position_tracker = PositionTracker(...) above) but never
        actually called anywhere in this codebase - this method was an independent, drifted
        duplicate of the exact same logic that was still live-wired into HandlerContext
        (update_position_with_retry_fn=self._update_position_with_retry) and used by
        ExitHandler for every real exit. The duplicate used float(result[1]) for the stop
        price instead of Decimal - directly contradicting PositionTracker's own comment
        ("Keep stop price as Decimal to avoid floating-point rounding errors in financial
        calculations") - and had no NULL guard on current_stop_price (would raise a bare
        TypeError instead of a clear ValueError). PositionTracker's version was the
        already-fixed one; it just was never wired in.
        """
        return self.position_tracker.update_position_with_retry(
            cur, position_id, new_qty, new_stop_price, full_exit, exit_stage,
            pnl_dollars=pnl_dollars, pnl_pct=pnl_pct, exit_reason=exit_reason
        )

    def exit_trade(
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
