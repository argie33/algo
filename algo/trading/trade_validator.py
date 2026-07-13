#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import logging
from datetime import date as _date
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from utils.infrastructure import EASTERN_TZ
from utils.trading import PositionStatus, TradeStatus

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

"""Trade validation logic extracted from monolithic Executor.

Validates trade preconditions and risk parameters before execution.
"""

logger = logging.getLogger(__name__)


def _validate_and_load_r_multiples(config: AlgoConfig | dict[str, Any]) -> tuple[float, float, float]:
    """Validate R-multiple config values and return as tuple.

    Raises ValueError if any required R-multiple is missing or None.
    """
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
    return (
        float(config["t1_target_r_multiple"]),
        float(config["t2_target_r_multiple"]),
        float(config["t3_target_r_multiple"]),
    )


class TradeValidator:
    """Validates trades against risk and operational constraints.

    Responsibilities:
    - Validate basic price/date/quantity inputs
    - Verify portfolio availability
    - Check pre-trade risk constraints
    - Validate stop loss and target prices
    - Detect duplicate positions and re-entry violations
    """

    def __init__(self, config: AlgoConfig | dict[str, Any], pretrade_checks: Any = None):
        """Initialize validator with configuration and pre-trade checks engine.

        Args:
            config: Trading configuration dict
            pretrade_checks: PreTradeChecks instance for risk validation
        """
        self.config = config
        self.pretrade_checks = pretrade_checks

        # Load and validate R-multiples (fail-fast)
        self.t1_target_r_multiple, self.t2_target_r_multiple, self.t3_target_r_multiple = _validate_and_load_r_multiples(config)

        # Validate re-entry config values
        if "max_reentries_per_name" not in config or config["max_reentries_per_name"] is None:
            raise ValueError("CRITICAL: max_reentries_per_name config missing or None.")
        self.max_reentries_per_name = int(config["max_reentries_per_name"])

        if "min_days_before_reentry_same_symbol" not in config or config["min_days_before_reentry_same_symbol"] is None:
            raise ValueError("CRITICAL: min_days_before_reentry_same_symbol config missing or None.")
        self.min_days_before_reentry_same_symbol = int(config["min_days_before_reentry_same_symbol"])

    def validate_entry_preconditions(  # noqa: C901 - validation of all trade parameters requires multiple checks
        self,
        symbol: str,
        entry_price: Decimal | float,
        stop_loss_price: Decimal | float,
        shares: Decimal | float,
        portfolio_value: Decimal | float | None,
        signal_date: _date | None = None,
        entry_date: _date | None = None,
        target_1_price: Decimal | float | None = None,
        target_2_price: Decimal | float | None = None,
        target_3_price: Decimal | float | None = None,
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Validate all entry trade preconditions before execution.

        Returns:
            (valid: bool, error_message: str|None, result_dict: dict with targets if auto-calculated)
        """
        entry_price = Decimal(str(entry_price))
        shares = Decimal(str(shares))
        stop_loss_price = Decimal(str(stop_loss_price))

        # Dates MUST be provided or explicitly None for default to current date
        # CRITICAL: Use ET (Eastern Time) for all trading dates, not UTC
        # Market hours are 9:30 AM - 4:00 PM ET, not UTC
        if signal_date is None:
            signal_date = datetime.now(EASTERN_TZ).date()
        elif not isinstance(signal_date, (_date, type(None))):
            raise ValueError(f"signal_date must be a date or None, got {type(signal_date).__name__}: {signal_date!r}")

        if entry_date is None:
            entry_date = datetime.now(EASTERN_TZ).date()
        elif not isinstance(entry_date, (_date, type(None))):
            raise ValueError(f"entry_date must be a date or None, got {type(entry_date).__name__}: {entry_date!r}")

        # Validate date ordering (signal_date guaranteed to be a date by this point)
        if entry_date is not None and signal_date is not None and entry_date < signal_date:
            return (
                False,
                f"Invalid: entry_date {entry_date} must be >= signal_date {signal_date}",
                {},
            )

        # Validate basic prices and quantities
        if entry_price <= 0:
            return False, f"Invalid entry price: {entry_price} (must be > 0)", {}
        if stop_loss_price <= 0:
            return (
                False,
                f"Invalid stop loss price: {stop_loss_price} (must be > 0)",
                {},
            )
        if shares <= 0:
            return False, f"Invalid share count: {shares} (must be > 0)", {}

        # Validate portfolio availability
        if not portfolio_value or portfolio_value <= 0:
            return (
                False,
                "Cannot execute trade: portfolio value unavailable from Alpaca and DB snapshot",
                {},
            )

        # Run pre-trade risk checks if available
        if self.pretrade_checks:
            position_value = shares * entry_price
            try:
                pretrade_passed, pretrade_reason = self.pretrade_checks.run_all(
                    symbol=symbol,
                    position_value=float(position_value),
                    portfolio_value=float(portfolio_value),
                    side="BUY",
                )
            except ValueError as e:
                return False, f"Pre-trade check failed: {e!s}", {}
            if not pretrade_passed:
                return False, f"Pre-trade check failed: {pretrade_reason}", {}

        # Validate stop loss price relative to entry
        stop_price_dec = Decimal(str(stop_loss_price))
        risk_per_share_decimal = entry_price - stop_price_dec
        if risk_per_share_decimal <= 0:
            return (
                False,
                f"Invalid stop: ${stop_loss_price:.2f} >= entry ${entry_price:.2f} (stop must be below entry)",
                {},
            )

        # Enforce minimum risk (1% below entry)
        if stop_price_dec >= entry_price * Decimal("0.99"):
            return (
                False,
                f"Stop too tight: ${stop_loss_price:.2f} within 1% of entry ${entry_price:.2f} (meaningful R required)",
                {},
            )

        # Auto-calculate missing targets or validate provided ones (using validated instance variables)
        result_dict = {}
        if target_1_price is None:
            t1_r_dec = Decimal(str(self.t1_target_r_multiple))
            target_1_price = (entry_price + (risk_per_share_decimal * t1_r_dec)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            result_dict["target_1_price"] = target_1_price
        else:
            target_1_price = Decimal(str(target_1_price))

        if target_2_price is None:
            t2_r_dec = Decimal(str(self.t2_target_r_multiple))
            target_2_price = (entry_price + (risk_per_share_decimal * t2_r_dec)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            result_dict["target_2_price"] = target_2_price
        else:
            target_2_price = Decimal(str(target_2_price))

        if target_3_price is None:
            t3_r_dec = Decimal(str(self.t3_target_r_multiple))
            target_3_price = (entry_price + (risk_per_share_decimal * t3_r_dec)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            result_dict["target_3_price"] = target_3_price
        else:
            target_3_price = Decimal(str(target_3_price))

        # Validate individual targets exceed entry
        if target_1_price <= entry_price:
            return (
                False,
                f"Invalid target_1: ${target_1_price:.2f} <= entry ${entry_price:.2f}",
                {},
            )
        if target_2_price <= entry_price:
            return (
                False,
                f"Invalid target_2: ${target_2_price:.2f} <= entry ${entry_price:.2f}",
                {},
            )
        if target_3_price <= entry_price:
            return (
                False,
                f"Invalid target_3: ${target_3_price:.2f} <= entry ${entry_price:.2f}",
                {},
            )

        # Validate target hierarchy
        if target_1_price >= target_2_price:
            return (
                False,
                f"Invalid target hierarchy: target_1 ${target_1_price:.2f} >= target_2 ${target_2_price:.2f}",
                {},
            )
        if target_2_price >= target_3_price:
            return (
                False,
                f"Invalid target hierarchy: target_2 ${target_2_price:.2f} >= target_3 ${target_3_price:.2f}",
                {},
            )

        return True, None, result_dict

    def check_duplicate_position(self, cur: Any, symbol: str) -> tuple[bool, str | None]:
        cur.execute(
            """
            SELECT symbol FROM algo_positions
            WHERE symbol = %s AND status = %s
            LIMIT 1
            """,
            (symbol, PositionStatus.OPEN.value),
        )
        if cur.fetchone():
            return (
                True,
                f"Symbol {symbol} already has an open position. Close it before entering another.",
            )
        return False, None

    def check_idempotent_duplicate(
        self,
        cur: Any,
        symbol: str,
        signal_date: _date,
        entry_price: Decimal | float,
        stop_loss_price: Decimal | float,
    ) -> tuple[bool, str | None, str | None]:
        """Check if trade already exists via idempotency key.

        Returns:
            (is_duplicate: bool, error_message: str|None, existing_trade_id: str|None)
        """
        key_source = f"{symbol}|{signal_date}|{entry_price}|{stop_loss_price}"
        idempotency_key = hashlib.sha256(key_source.encode()).hexdigest()

        cur.execute(
            "SELECT trade_id FROM algo_trades WHERE idempotency_key = %s LIMIT 1",
            (idempotency_key,),
        )
        result = cur.fetchone()
        if result:
            trade_id = result[0]
            logger.warning(f"DUPLICATE EXECUTION BLOCKED: Idempotency key exists for {symbol} (trade_id: {trade_id})")
            return (
                True,
                f"Trade already exists for {symbol} on {signal_date} (idempotent duplicate)",
                trade_id,
            )
        return False, None, None

    def check_open_position_in_symbol(self, cur: Any, symbol: str) -> tuple[bool, str | None]:
        cur.execute(
            "SELECT 1 FROM algo_positions WHERE symbol = %s AND status = %s LIMIT 1",
            (symbol, PositionStatus.OPEN.value),
        )
        if cur.fetchone():
            return True, f"Already have open position in {symbol}"
        return False, None

    def check_signal_fingerprint_duplicate(
        self,
        cur: Any,
        symbol: str,
        signal_date: _date,
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> tuple[bool, str | None, str | None]:
        """Check if same signal already exists as OPEN or PENDING trade.

        Returns:
            (is_duplicate: bool, error_message: str|None, existing_trade_id: str|None)
        """
        # CRITICAL: signal_date is required for fingerprint matching — no fallback to default date
        if signal_date is None:
            raise ValueError(
                f"signal_date required for {symbol} duplicate check. "
                f"Cannot match trades without valid signal date — this is a data integrity requirement."
            )

        cur.execute(
            """
            SELECT trade_id FROM algo_trades
            WHERE symbol = %s AND signal_date = %s
              AND status IN (%s, %s)
            LIMIT 1
            """,
            (symbol, signal_date, TradeStatus.OPEN.value, TradeStatus.PENDING.value),
        )
        result = cur.fetchone()
        if result:
            trade_id = result[0]
            signal_fingerprint = f"{symbol}|{entry_price:.2f}|{stop_loss_price:.2f}|{signal_date}"
            logger.warning(f"DUPLICATE SIGNAL: {signal_fingerprint} (prior trade: {trade_id})")
            return (
                True,
                f"Trade already exists for {symbol} on {signal_date} (fingerprint: {signal_fingerprint})",
                trade_id,
            )
        return False, None, None

    def check_pending_trades(self, cur: Any, symbol: str) -> tuple[bool, str | None, int]:
        from algo.infrastructure.config.sql_intervals import get_interval_sql

        interval_sql = get_interval_sql("30d")
        cur.execute(
            f"""
            SELECT COUNT(*) FROM algo_trades
            WHERE symbol = %s AND status IN (%s, %s)
              AND created_at >= CURRENT_TIMESTAMP - {interval_sql}
            """,
            (symbol, TradeStatus.OPEN.value, TradeStatus.PENDING.value),
        )
        result = cur.fetchone()
        if result is None:
            raise RuntimeError(
                f"[PENDING_TRADES] Unexpected NULL from database for {symbol} pending trade count. "
                f"Database query integrity failure — cannot safely determine if duplicate entry exists."
            )
        pending_count = result[0]
        if pending_count > 0:
            return (
                True,
                f"{symbol}: {pending_count} pending/open trade(s) exist. Close before re-entering.",
                pending_count,
            )
        return False, None, 0

    def check_reentry_rules(self, cur: Any, symbol: str) -> tuple[bool, str | None, int]:
        from algo.infrastructure.config.sql_intervals import get_interval_sql

        interval_sql = get_interval_sql("30d")
        # Find most recent CLOSED trade in the last 30 days
        cur.execute(
            f"""
            SELECT trade_id, exit_date, exit_reason, profit_loss_pct, reentry_count
            FROM algo_trades
            WHERE symbol = %s AND status = %s
              AND exit_date >= CURRENT_DATE - {interval_sql}
            ORDER BY exit_date DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (symbol, TradeStatus.CLOSED.value),
        )
        prior = cur.fetchone()
        reentry_count = 0
        if prior:
            _prior_trade_id, exit_date, exit_reason, _exit_pnl, prior_reentry = prior

            # CRITICAL: reentry_count MUST be present in database, no fallback to 0
            if prior_reentry is None:
                raise ValueError(
                    f"[REENTRY_COUNT_MISSING] Trade data integrity error for {symbol}: "
                    f"reentry_count is NULL in database. Cannot safely determine re-entry eligibility."
                )

            # CRITICAL: exit_reason MUST be present for stop-out detection, no fallback to empty string
            if exit_reason is None:
                raise ValueError(
                    f"[EXIT_REASON_MISSING] Trade data integrity error for {symbol}: "
                    f"exit_reason is NULL. Cannot determine if prior exit was a stop-out."
                )

            # Only enforce re-entry rules if prior trade was a stop-out
            if "STOP" in exit_reason.upper() or "TIME" in exit_reason.upper():
                prior_reentry_count = int(prior_reentry)
                if prior_reentry_count >= self.max_reentries_per_name:
                    return (
                        False,
                        f"{symbol}: {prior_reentry_count} prior re-entries within 30 days >= {self.max_reentries_per_name} max",
                        0,
                    )

                # Enforce minimum days between stop-out and re-entry (using validated instance variable)
                if exit_date:
                    exit_d = exit_date if isinstance(exit_date, _date) else exit_date.date()
                    days_since_exit = (datetime.now(timezone.utc).date() - exit_d).days
                    if days_since_exit < self.min_days_before_reentry_same_symbol:
                        return (
                            False,
                            f"{symbol}: only {days_since_exit}d since stop-out; require {self.min_days_before_reentry_same_symbol}d before re-entry (reset period)",
                            0,
                        )
                reentry_count = prior_reentry_count + 1

        return True, None, reentry_count
