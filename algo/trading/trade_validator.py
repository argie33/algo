#!/usr/bin/env python3
from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from utils.infrastructure import EASTERN_TZ
from utils.trading import TradeStatus

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
        self.t1_target_r_multiple, self.t2_target_r_multiple, self.t3_target_r_multiple = (
            _validate_and_load_r_multiples(config)
        )

        # Validate re-entry config values
        if "max_reentries_per_name" not in config or config["max_reentries_per_name"] is None:
            raise ValueError("CRITICAL: max_reentries_per_name config missing or None.")
        self.max_reentries_per_name = int(config["max_reentries_per_name"])

        if "min_days_before_reentry_same_symbol" not in config or config["min_days_before_reentry_same_symbol"] is None:
            raise ValueError("CRITICAL: min_days_before_reentry_same_symbol config missing or None.")
        self.min_days_before_reentry_same_symbol = int(config["min_days_before_reentry_same_symbol"])

        # REAL-MONEY-READINESS FIX (2026-09-06 audit): see check_reentry_rules' own comment -
        # a separate, longer cooldown that only applies on top of the reset period above when
        # the prior exit was a LOSS (wash-sale rule), not a blanket replacement for it.
        if "wash_sale_cooldown_days" not in config or config["wash_sale_cooldown_days"] is None:
            raise ValueError("CRITICAL: wash_sale_cooldown_days config missing or None.")
        self.wash_sale_cooldown_days = int(config["wash_sale_cooldown_days"])

    def validate_entry_preconditions(
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
        try:
            return self._validate_entry_preconditions_impl(
                symbol,
                entry_price,
                stop_loss_price,
                shares,
                portfolio_value,
                signal_date,
                entry_date,
                target_1_price,
                target_2_price,
                target_3_price,
            )
        except InvalidOperation as e:
            # BUG FOUND 2026-08-11: a NaN/Infinity-tainted entry_price/stop_loss_price/shares
            # (e.g. from a bad ATR/price calculation upstream) survives `Decimal(str(x))`
            # construction, but a NaN Decimal RAISES on ordering comparisons like `<= 0`
            # instead of silently returning False the way float NaN does - see
            # position_sizer.py's calculate_position_size() for the same bug class, already
            # fixed there. This function's own per-signal caller in phase8_entry_execution.py
            # only catches (RuntimeError, ValueError, TypeError, AttributeError, IndexError,
            # psycopg2.Error, DatabaseError) around each signal - decimal.InvalidOperation
            # (an ArithmeticError) isn't in that list, so one symbol with a NaN price would
            # propagate out of the per-signal loop entirely and abort entry execution for
            # every OTHER qualified signal that day, not just the bad one. Converting to this
            # function's own documented (bool, str, dict) contract instead.
            return False, f"Invalid entry parameters (NaN/Infinity): {type(e).__name__}: {e}", {}

    def _validate_entry_preconditions_impl(  # noqa: C901 - validation of all trade parameters requires multiple checks
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
        entry_price = Decimal(str(entry_price))
        shares = Decimal(str(shares))
        stop_loss_price = Decimal(str(stop_loss_price))
        # BUG FOUND 2026-08-25 (real-money-readiness goal session, entry-validation audit):
        # portfolio_value was excluded from this finiteness check - it's Optional (None is a
        # real, expected "unavailable" case handled separately below), but a non-None NaN/Inf
        # value would silently slip through undetected. A float NaN is truthy (`not
        # float("nan")` is False) and `float("nan") <= 0` is always False (NaN comparisons
        # never raise/trip in Python), so the `if not portfolio_value or portfolio_value <=
        # 0:` guard a few lines below this one would NOT catch it - the exact same
        # NaN-comparison-guard bug class already found and fixed this session elsewhere
        # (position_sizer.py, order_manager.py, exit_engine.py, phase8_entry_execution.py).
        # Converting to Decimal here (matching entry_price/stop_loss_price/shares) is doubly
        # safe: Decimal("nan").is_finite() correctly reports False, closing the gap those
        # float comparisons would have missed.
        portfolio_value_dec = Decimal(str(portfolio_value)) if portfolio_value is not None else None

        # Infinity (unlike NaN) doesn't raise on Decimal ordering comparisons - `Decimal(
        # "Infinity") <= 0` is a well-defined False, so the `<= 0` checks below don't catch
        # it. Left unchecked, infinite shares/prices would pass validation here and only
        # surface later as a much-less-obvious InvalidOperation out of a downstream
        # `.quantize()` call (target price calculation), or worse, propagate into real
        # position-value/risk math. Reject explicitly, at the same point NaN is implicitly
        # rejected by the caller's try/except.
        finiteness_checks = [
            ("entry_price", entry_price),
            ("stop_loss_price", stop_loss_price),
            ("shares", shares),
        ]
        if portfolio_value_dec is not None:
            finiteness_checks.append(("portfolio_value", portfolio_value_dec))
        for label, value in finiteness_checks:
            if not value.is_finite():
                return False, f"Invalid {label}: {value} (must be a finite number)", {}

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

        # Validate portfolio availability (portfolio_value_dec already NaN/Inf-checked above)
        if not portfolio_value_dec or portfolio_value_dec <= 0:
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
                    portfolio_value=float(portfolio_value_dec),
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

    def check_duplicate_position(
        self, cur: Any, symbol: str, entry_date: _date | None = None
    ) -> tuple[bool, str | None]:
        # CRITICAL FIX (2026-08-06): Check for same-day duplicate entries by looking at algo_positions,
        # not just open trades in algo_trades. When a position is closed and immediately re-entered
        # on the same trading day, the algo_trades status becomes 'closed', allowing the duplicate check
        # to pass and create multiple positions for the same symbol on the same date. This corrupts
        # portfolio tracking, risk calculations, and exit execution.
        #
        # If entry_date is provided, enforce one position per symbol per trading day (the constraint).
        # If not provided (backward compat), fall back to open-trades-only check for live positions.

        if entry_date:
            # NEW CHECK: Prevent same-day duplicate entries at algo_positions level
            # "You can only hold one position per symbol per trading day" constraint
            # CRITICAL FIX: Only block if position is OPEN, not CLOSED. If the previous position was
            # already exited, re-entry should be allowed (unless cooldown/re-entry rules apply).
            # Previous bug: Checked ALL positions regardless of status, blocking re-entry even after
            # the first position closed, which prevented Phase 8 from entering any new positions.
            cur.execute(
                """
                SELECT position_id FROM algo_positions
                WHERE symbol = %s AND entry_date = %s AND is_open = true
                LIMIT 1
                """,
                (symbol, entry_date),
            )
            if cur.fetchone():
                return (
                    True,
                    f"Symbol {symbol} already has an active (open) position entered on {entry_date}. "
                    f"Can only hold one open position per symbol per trading day.",
                )

        # LEGACY CHECK: Also check for truly open live positions
        # This catches cases where entry_date is not provided or handles the general "already open" case.
        open_statuses = TradeStatus.all_open()
        cur.execute(
            """
            SELECT trade_id FROM algo_trades
            WHERE symbol = %s AND status = ANY(%s)
            LIMIT 1
            """,
            (symbol, list(open_statuses)),
        )
        if cur.fetchone():
            return (
                True,
                f"Symbol {symbol} already has an open trade. Close it before entering another.",
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
        """Check if trade already exists for this symbol+signal_date+entry_price+stop (one entry per signal per day).

        Returns:
            (is_duplicate: bool, error_message: str|None, existing_trade_id: str|None)
        """
        # Check OPEN trades to prevent multiple active positions in same symbol on same signal date
        open_statuses = TradeStatus.all_open()
        cur.execute(
            """
            SELECT id FROM algo_trades
            WHERE symbol = %s AND signal_date = %s
            AND status = ANY(%s)
            LIMIT 1
            """,
            (symbol, signal_date, list(open_statuses)),
        )
        result = cur.fetchone()
        if result:
            trade_id = result[0]
            logger.warning(
                f"DUPLICATE EXECUTION BLOCKED: Open trade exists for {symbol} on {signal_date} (id: {trade_id})"
            )
            return (
                True,
                f"Trade already exists for {symbol} on {signal_date} (idempotent duplicate)",
                str(trade_id),
            )

        # Check for identical trade parameters IF STILL OPEN to prevent duplicate ACTIVE positions.
        # If the prior trade with identical entry_price+stop_loss_price is CLOSED, allow re-entry
        # (subject to cooldown/re-entry rules). If it's still OPEN, block to prevent double-entry.
        # Previous bug: Checked ALL trades regardless of status, blocking re-entry even after the
        # prior trade closed. This prevented Phase 8 from executing any new trades with same entry params.
        entry_price_dec = Decimal(str(entry_price))
        stop_loss_dec = Decimal(str(stop_loss_price))
        open_statuses = TradeStatus.all_open()
        cur.execute(
            """
            SELECT id, status FROM algo_trades
            WHERE symbol = %s AND signal_date = %s
            AND entry_price = %s AND stop_loss_price = %s
            AND status = ANY(%s)
            LIMIT 1
            """,
            (symbol, signal_date, entry_price_dec, stop_loss_dec, list(open_statuses)),
        )
        result = cur.fetchone()
        if result:
            trade_id, status = result
            logger.info(
                f"SKIPPING {symbol}: active trade with identical parameters exists (id: {trade_id}, status: {status}). "
                f"Entry=${entry_price_dec}, Stop=${stop_loss_dec}, Date={signal_date}"
            )
            return (
                True,
                f"Active trade with identical parameters already exists for {symbol} (status={status})",
                str(trade_id),
            )

        return False, None, None

    def check_open_position_in_symbol(self, cur: Any, symbol: str) -> tuple[bool, str | None]:
        # CRITICAL FIX: Must check algo_trades for live status, not algo_positions.
        # The constraint algo_trades_symbol_live_status_idx (migration 1158) enforces at the
        # algo_trades level. Checking algo_positions only catches manually-tracked positions
        # but misses entries in algo_trades with any non-terminal status - not just 'open':
        # a live (execution_mode=auto) filled order writes status='filled'/'partially_filled'
        # literally, so a status='open'-only check here would miss it entirely.
        open_statuses = TradeStatus.all_open()
        cur.execute(
            "SELECT trade_id FROM algo_trades WHERE symbol = %s AND status = ANY(%s) LIMIT 1",
            (symbol, list(open_statuses)),
        )
        if cur.fetchone():
            return True, f"Already have open position in {symbol} (existing trade in progress)"
        return False, None

    def check_signal_fingerprint_duplicate(
        self,
        cur: Any,
        symbol: str,
        signal_date: _date,
        entry_price: Decimal,
        stop_loss_price: Decimal,
    ) -> tuple[bool, str | None, str | None]:
        """Check if same signal already exists as a live (non-terminal) trade.

        CRITICAL FIX: The database constraint algo_trades_symbol_live_status_idx
        (migration 1158) only allows ONE live trade per symbol (regardless of signal_date).
        This check MUST reject ANY live trade for the symbol, not just same-date duplicates -
        and must use TradeStatus.all_open(), not just OPEN/PENDING, since a live
        (execution_mode=auto) filled order writes status='filled'/'partially_filled' literally.

        Returns:
            (is_duplicate: bool, error_message: str|None, existing_trade_id: str|None)
        """
        # CRITICAL: signal_date is required for fingerprint matching - no fallback to default date
        if signal_date is None:
            raise ValueError(
                f"signal_date required for {symbol} duplicate check. "
                f"Cannot match trades without valid signal date - this is a data integrity requirement."
            )

        # Check for ANY live trade with this symbol (database constraint enforces 1 max)
        open_statuses = TradeStatus.all_open()
        cur.execute(
            """
            SELECT trade_id, signal_date FROM algo_trades
            WHERE symbol = %s
              AND status = ANY(%s)
            LIMIT 1
            """,
            (symbol, list(open_statuses)),
        )
        result = cur.fetchone()
        if result:
            trade_id, prior_signal_date = result[0], result[1]
            signal_fingerprint = f"{symbol}|{entry_price:.2f}|{stop_loss_price:.2f}|{signal_date}"
            prior_fingerprint = f"{symbol}|{prior_signal_date}" if prior_signal_date else f"{symbol}|[no signal_date]"
            logger.warning(
                f"DUPLICATE SIGNAL: {signal_fingerprint} (prior trade: {trade_id}, prior_signal: {prior_fingerprint})"
            )
            return (
                True,
                f"Already have open trade for {symbol} (trade_id: {trade_id}, prior signal_date: {prior_signal_date}). "
                f"Cannot have multiple open positions in same symbol.",
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
                f"Database query integrity failure - cannot safely determine if duplicate entry exists."
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
        # REAL-MONEY-READINESS FIX (2026-09-06 audit): lookback window widened from a fixed
        # 30 days to max(30, wash_sale_cooldown_days) - a straight 30-day window could miss a
        # loss-exit sitting right at day 30/31, which is exactly the case the wash-sale check
        # below needs to see in order to enforce the longer cooldown. Parameterized (not the
        # sql_intervals.py fixed-key helper this used before) since the window is now a
        # runtime-configurable value, not one of that module's fixed registered keys.
        lookback_days = max(30, self.wash_sale_cooldown_days)
        lookback_date = datetime.now(EASTERN_TZ).date() - timedelta(days=lookback_days)
        # Find most recent CLOSED trade within the lookback window
        cur.execute(
            """
            SELECT trade_id, exit_date, exit_reason, profit_loss_pct, reentry_count
            FROM algo_trades
            WHERE symbol = %s AND status = %s
              AND exit_date >= %s
            ORDER BY exit_date DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (symbol, TradeStatus.CLOSED.value, lookback_date),
        )
        prior = cur.fetchone()
        reentry_count = 0
        if prior:
            _prior_trade_id, exit_date, exit_reason, exit_pnl, prior_reentry = prior

            # If reentry_count is NULL, treat as 0 (no prior re-entries)
            prior_reentry = prior_reentry if prior_reentry is not None else 0

            # If exit_reason is NULL, treat as non-stop-out (not a stop-loss exit)
            # This allows re-entry instead of blocking with an error
            is_stop_out = False
            if exit_reason is not None:
                # Only enforce re-entry rules if prior trade was a stop-out
                is_stop_out = "STOP" in exit_reason.upper() or "TIME" in exit_reason.upper()

            if is_stop_out:
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
                    # CRITICAL FIX: this compared exit_d (an ET trading date - see signal_date/
                    # entry_date defaults above, both datetime.now(EASTERN_TZ).date(), the
                    # convention this whole file uses) against a UTC calendar date. Between
                    # ~7pm-midnight ET, UTC's date has already rolled to the next day while the
                    # ET trading date hasn't, so days_since_exit read one day too HIGH - an
                    # evening/afterhours run could let a re-entry through one day earlier than
                    # min_days_before_reentry_same_symbol actually requires. Use the same
                    # EASTERN_TZ convention as the rest of this file for internal consistency.
                    days_since_exit = (datetime.now(EASTERN_TZ).date() - exit_d).days

                    # REAL-MONEY-READINESS FIX (2026-09-06 audit): min_days_before_reentry_
                    # same_symbol alone is a pure flip-flop-prevention reset period with no
                    # tax awareness - re-entering the same symbol 6-29 days after a LOSS-
                    # driven stop-out (which the base 5-day reset already permits) triggers
                    # the IRS wash-sale rule (30-day window before/after a loss sale),
                    # disallowing that loss for tax purposes in a taxable account. Wash sale
                    # only applies to LOSSES, not gains - a profitable stop-out (e.g. a
                    # trailing stop) has no tax concern here and only waits the shorter base
                    # reset period. required_cooldown_days is the base reset UNLESS this was
                    # a loss, in which case it's whichever is longer.
                    is_loss_exit = exit_pnl is not None and float(exit_pnl) < 0
                    required_cooldown_days = self.min_days_before_reentry_same_symbol
                    cooldown_reason = "reset period"
                    if is_loss_exit and self.wash_sale_cooldown_days > required_cooldown_days:
                        required_cooldown_days = self.wash_sale_cooldown_days
                        cooldown_reason = "wash-sale cooldown - prior exit was a loss"

                    if days_since_exit < required_cooldown_days:
                        return (
                            False,
                            f"{symbol}: only {days_since_exit}d since stop-out; require {required_cooldown_days}d before re-entry ({cooldown_reason})",
                            0,
                        )
                reentry_count = prior_reentry_count + 1

        return True, None, reentry_count
