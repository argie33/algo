#!/usr/bin/env python3
"""
Position Monitor - Institutional-grade daily position health checks

Runs each trading day on every open position. For each one:
  1. Refresh current price + position value + unrealized P&L
  2. Recompute trailing stop using ATR / swing low / 50-DMA - STOPS ONLY GO UP
  3. Score position health across factors:
        a. Relative strength vs SPY (degrading = warning)
        b. Sector strength (turned weak = warning)
        c. Distance from peak unrealized (giving back gains = warning)
        d. Time decay (over half of max_hold without progress = warning)
        e. Earnings proximity (block_window approaching = warning)
        f. Distribution day count
  4. Aggregate health flags. >= halt_flag_count -> propose early exit.
  5. Persist updated state on algo_positions and write audit entries.

The monitor PROPOSES adjustments - actual stop-raising executes via
TradeExecutor.exit_trade(new_stop_price=...) in the orchestrator.
"""

from __future__ import annotations

import logging
import math

# time/requests are re-imported "as" themselves (PEP 484 explicit-reexport idiom) rather than
# plain `import time`/`import requests`: position_order_management.py's _cancel_on_alpaca/
# check_stale_orders reference them lazily as _pm.time/_pm.requests (see that module's
# docstring) so existing tests can keep patching
# "algo.monitoring.position_monitor.time.sleep"/".requests.delete" - a plain import here has
# no other local use since the methods that used to call them directly moved out, and this
# repo's ruff config disallows bare unused-import suppressions (see pyproject.toml's
# per-file-ignores comment), so the module must be kept alive via an explicit re-export instead.
import time as time
from collections.abc import Callable
from datetime import date as _date
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

import psycopg2
import requests as requests
from psycopg2.extensions import cursor as PsycopgCursor

# Same explicit-reexport reasoning as time/requests above: get_alpaca_base_url/
# get_alpaca_credentials are only used lazily via _pm.get_alpaca_base_url/_pm.get_alpaca_credentials
# from position_order_management.py now that _cancel_on_alpaca moved out of this module.
from algo.config.api_endpoints import get_alpaca_base_url as get_alpaca_base_url
from algo.config.credential_manager import get_alpaca_credentials as get_alpaca_credentials
from algo.infrastructure.market_calendar import MarketCalendar
from utils.db import DatabaseContext

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

logger = logging.getLogger(__name__)


class PositionValidationError(Exception):
    """Raised when a position fails validation and cannot be monitored."""


# Imported here (not at module top) because position_corporate_actions.py (and the other
# mixin modules below) import PositionValidationError from this module - placing this import
# before that class exists would be a circular-import failure.
from algo.monitoring.position_corporate_actions import CorporateActionsMixin  # noqa: E402
from algo.monitoring.position_health_checks import PositionHealthChecksMixin  # noqa: E402
from algo.monitoring.position_market_data import PositionMarketDataMixin  # noqa: E402
from algo.monitoring.position_order_management import PositionOrderManagementMixin  # noqa: E402
from algo.monitoring.position_reporting import PositionReportingMixin  # noqa: E402


class PositionMonitor(
    PositionOrderManagementMixin,
    PositionHealthChecksMixin,
    PositionMarketDataMixin,
    PositionReportingMixin,
    CorporateActionsMixin,
):
    """Daily position health checker and stop adjuster."""

    def _with_cursor(
        self,
        operation: Callable[[PsycopgCursor[Any]], Any],
        mode: str = "read",
        cur: PsycopgCursor[Any] | None = None,
    ) -> Any:
        """Execute operation with cursor via DatabaseContext or passed cursor.

        CRITICAL: If cur is passed by caller, NEVER open a new DatabaseContext.
        Opening a new context closes the caller's connection and breaks their cursor.
        This helper must be context-aware: if a cursor was passed, use it.
        If not passed (None), create a new context as fallback.

        Args:
            operation: Function to execute with cursor
            mode: Database mode ("read" or "write") - only used if creating new context
            cur: Optional cursor from caller. If provided, use this instead of creating new.

        Returns:
            Result from operation
        """
        if cur is not None:
            # Caller passed a cursor - use it directly, never open new context
            return operation(cur)
        else:
            # No cursor passed - create new context (safe fallback for standalone calls)
            with DatabaseContext(mode) as new_cur:
                return operation(new_cur)

    def __init__(self, config: AlgoConfig) -> None:
        self.config = config

    def review_positions(  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
        self, current_date: _date | None = None, cur: PsycopgCursor[Any] | None = None
    ) -> list[dict[str, Any]]:
        """Review every open position. Returns list of recommendations.

        Args:
            current_date: Date to review positions for (defaults to today)
            cur: Optional database cursor. If provided, uses it instead of opening new context (prevents nested context exhaustion).
        """
        if current_date is None:
            current_date = _date.today()

        def _review_with_cursor(cursor: PsycopgCursor[Any]) -> list[dict[str, Any]]:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
            recs = []
            logger.info("[POSITION_MONITOR] review_positions: cursor acquired")
            try:
                # CRITICAL FIX 2026-08-09: bound by current_date - an unbounded "latest
                # snapshot" query picks up any stray future-dated row (e.g. a leftover
                # local --date simulation snapshot) ahead of the real current one. See
                # algo/risk/circuit_breaker.py for the same bug class.
                cursor.execute(
                    """
                    SELECT total_portfolio_value FROM algo_portfolio_snapshots
                    WHERE snapshot_date <= %s
                    ORDER BY snapshot_date DESC LIMIT 1
                """,
                    (current_date,),
                )
                eq_row = cursor.fetchone()

                if eq_row is None or eq_row[0] is None:
                    raise PositionValidationError(
                        "[POSITION_MONITOR CRITICAL] Portfolio snapshot unavailable. "
                        "Cannot monitor positions without accurate account equity from Phase 9 reconciliation. "
                        "Fallback estimates ($100k dummy, position-value extrapolation) violate fail-fast principle. "
                        "Position monitoring depends on real broker account data, not guesses. "
                        "Verify Phase 9 (reconciliation) completed successfully, then retry this orchestrator run."
                    )
                else:
                    total_equity = float(eq_row[0])
                if total_equity <= 0:
                    raise PositionValidationError(
                        f"Invalid portfolio equity: {total_equity} <= 0. Cannot monitor positions with zero or negative equity."
                    )

                # Compute margin usage = (equity - buying_power) / equity
                # Using proxy: if total open position value > 90% of equity, halt new entries
                cursor.execute("""
                    SELECT COUNT(*), SUM(position_value) FROM algo_positions WHERE status = 'open'
                """)
                count_row = cursor.fetchone()
                if count_row is None:
                    raise PositionValidationError("Query for open positions returned None - database error")
                if len(count_row) < 2:
                    raise PositionValidationError(
                        f"Position count query returned {len(count_row)} columns, expected 2 (COUNT, SUM). "
                        "Database schema or query result structure corruption detected."
                    )
                position_count = count_row[0]
                pos_value_sum = count_row[1]

                # CRITICAL: If we have open positions but position_value is NULL, that's data corruption
                if position_count > 0 and pos_value_sum is None:
                    raise PositionValidationError(
                        f"CRITICAL: {position_count} open positions exist but SUM(position_value) is NULL. "
                        "Database corruption detected. Margin calculation halted."
                    )

                # NULL sum means no open positions (SUM of empty set is NULL, not 0)
                pos_value = float(pos_value_sum) if pos_value_sum is not None else 0.0
                if pos_value < 0:
                    logger.error(
                        f"[MARGIN_CHECK] Total position value {pos_value:.2f} < 0 - "
                        "likely stale short position in algo_positions. "
                        "Reconciliation (Phase 4) will close it. Continuing with pos_value=0."
                    )
                    pos_value = 0.0

                margin_util_pct = pos_value / total_equity * 100
                if margin_util_pct > 90:
                    logger.critical(
                        f"[MARGIN HALT] Position value {margin_util_pct:.1f}% of equity - liquidation risk imminent"
                    )
                    raise PositionValidationError(
                        f"Margin utilization critical: {margin_util_pct:.1f}% of equity (>90%). Cannot proceed with position monitoring."
                    )
                elif margin_util_pct > 80:
                    logger.warning(f"[MARGIN WARNING] Position value {margin_util_pct:.1f}% of equity > 80%")
            except PositionValidationError:
                raise
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as margin_e:
                raise PositionValidationError(
                    f"Margin validation failed: {margin_e}. Cannot proceed without valid margin check."
                ) from margin_e

            try:
                logger.info(
                    "[POSITION_MONITOR] Calling check_sector_concentration with shared cursor (cursor lifecycle fix)"
                )
                # CRITICAL FIX: Pass cursor to avoid nested DatabaseContext closing our cursor
                conc = self.check_sector_concentration(current_date, cur=cursor)

                if conc["status"] == "HIGH_CONCENTRATION":
                    logger.info("  [WARNING]  Portfolio concentration risk detected")
            except RuntimeError as conc_e:
                raise PositionValidationError(
                    f"Sector concentration check failed: {conc_e}. Cannot proceed without valid concentration metrics."
                ) from conc_e

            # WIRED IN 2026-09-05 (real-money-readiness audit): check_corporate_actions()
            # (stock-split detection/rescale) existed as a fully-implemented method with zero
            # real callers anywhere in the orchestrator/phases/lambda/scripts - only its own
            # unit tests ever invoked it, directly, bypassing this entire call path. A real
            # stock split on an open position had NO mechanism to ever rescale its stop price
            # or quantity - it would sit at the wrong price scale (e.g. ~2x too high/low after
            # a 2:1 split) indefinitely, a genuinely unprotected/mis-protected position with
            # real money at risk. Runs before the FOR UPDATE position query below so any split
            # is rescaled first, and _evaluate_position reads the corrected values rather than
            # stale pre-split ones. Same PositionValidationError-wrapping pattern as the
            # margin/concentration checks above - a DB error here means position quantities
            # can't be verified against the broker, which must fail closed, not proceed with
            # potentially stale/wrong quantities and stops.
            try:
                logger.info("[POSITION_MONITOR] Checking for corporate actions (stock splits)")
                corp_actions = self.check_corporate_actions()
                if corp_actions:
                    logger.warning(f"[POSITION_MONITOR] Corporate action adjustments applied: {corp_actions}")
            except PositionValidationError:
                raise
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as corp_action_e:
                raise PositionValidationError(
                    f"Corporate action detection failed: {corp_action_e}. Cannot proceed without "
                    "verifying position quantities against the broker."
                ) from corp_action_e

            # NOTE: this queries algo_positions.status, not algo_trades.status - a separate,
            # already-normalized PositionStatus enum that every entry path (including
            # paper_pending/paper mode) writes as 'open' for any genuinely open position
            # (see test_entry_handler_paper_pending_position_status.py). It doesn't need
            # TradeStatus.all_open()'s multi-value IN-clause the way algo_trades-status
            # queries (exit_engine.py, circuit_breaker.py) do.
            # CRITICAL FIX 2026-08-02: Add FOR UPDATE locking to prevent TOCTOU race with Phase 6
            # If Phase 6 (exit_engine) runs concurrently in Lambda/ECS:
            # Without lock: Phase 3 reads -> Phase 6 modifies -> Phase 3 evaluates stale data
            # With lock: Phase 3 locks positions -> Phase 6 must wait -> reads current state
            #
            # CRITICAL FIX (2026-08-03): the column-count fix in the commit above (matching
            # this SELECT's column count to _evaluate_position()'s 14-value unpack) replaced
            # the query's 11th column with a literal NULL - which _evaluate_position() unpacks
            # into `target_hits`, then unconditionally raises if it's None ("target_hits is
            # NULL in algo_trades... Database schema or trade data corrupted"). So this query
            # NEVER supplied a real target_hits value, meaning review_positions() raised for
            # EVERY real open position, unconditionally - invisible all session because there
            # were zero real open positions in this dev environment to exercise the path until
            # an end-to-end synthetic verification test inserted one. Select the real
            # `p.target_levels_hit` column here instead (NOT NULL in the schema).
            # CRITICAL FIX: algo_positions has TWO trade-reference columns - the dead
            # `trade_ids` (varchar) column, never written by any code path (verified via
            # repo-wide grep: only executor_entry_handler.py's INSERT populates the real
            # one), and `trade_ids_arr` (the actual array column every other consumer -
            # Phase 6/8/9, circuit_breaker.py, exposure_policy.py, executor_exit_handler.py,
            # exit_engine.py, position_sizer.py - joins against). Selecting `trade_ids` here
            # silently produced trade_id=None for every real position (visible in the
            # 2026-08-03 fix's own audit-log JSON), not a crash but a quiet dead field.
            # CRITICAL FIX: this SELECT's 13th column (unpacked below into `current_stop`,
            # used as `active_stop` for every STOP_LOSS_HIT/trailing-stop decision in
            # _evaluate_position) selected `p.stop_loss_price` again instead of
            # `p.current_stop_price` - the SAME frozen entry-time value as the 4th column
            # (`init_stop`), never the live trailing stop that `_raise_stop()` actually
            # updates. Since `active_stop = float(current_stop) if current_stop else
            # init_stop` always received the identical frozen value, Phase 3's entire
            # STOP_LOSS_HIT check silently ignored every stop-raise ever applied to a
            # position - comparing current price against the ORIGINAL stop forever, not the
            # real, currently-enforced one. Confirmed live 2026-08-03: DAC's real
            # current_stop_price ($125.83, 6% below current price - safe) vs its frozen
            # stop_loss_price ($135.43, above current price) produced a false STOP_LOSS_HIT
            # recommendation for a healthy position. Depending on a given position's specific
            # stop-loss/current-stop divergence at any moment, this could equally mask a real
            # stop breach (false negative) as well as fabricate one (false positive) - the
            # comparison was against the wrong column either way.
            cursor.execute(
                """
                SELECT p.id, p.symbol, p.entry_price, p.stop_loss_price,
                       p.target_1_price, p.target_2_price, p.target_3_price,
                       p.entry_date, p.created_at,
                       p.quantity, p.target_levels_hit, p.trade_ids_arr,
                       p.current_stop_price, p.current_price
                FROM algo_positions p
                WHERE p.status = 'open' AND p.quantity > 0
                FOR UPDATE OF p
                """
            )
            positions = cursor.fetchall()

            logger.info(f"\n{'=' * 70}")
            logger.info(f"POSITION MONITOR - {current_date}")
            logger.info(f"{'=' * 70}")
            logger.info(f"Reviewing {len(positions)} open position(s)\n")

            validation_errors = []
            for i, row in enumerate(positions):
                try:
                    rec = self._evaluate_position(row, current_date, cur=cursor)
                except PositionValidationError as e:
                    # SAFETY: Validate row structure before accessing indices
                    # The SELECT query returns 14 columns (indices 0-13), so row must have exactly 14 elements
                    if row is None or not isinstance(row, (tuple, list)):
                        logger.error(
                            f"[PHASE 3] Row is None or not a tuple/list. Got {type(row).__name__}. "
                            f"Cannot extract position data. Database connection may be broken."
                        )
                        raise RuntimeError(
                            f"Position row is invalid type {type(row).__name__}. "
                            f"Database query may have failed or returned corrupted data."
                        ) from e
                    if len(row) < 10:  # Minimum needed: indices 0, 1, 9
                        logger.error(
                            f"[PHASE 3] Row has insufficient columns ({len(row)}, need at least 10 for indices 0,1,9). "
                            f"Cannot extract position data. Possible database query result corruption or schema drift."
                        )
                        raise RuntimeError(
                            f"Position row has {len(row)} columns, expected at least 10. "
                            f"Cannot extract position data. This may indicate database connection issues or schema mismatch."
                        ) from e
                    if len(row) != 14:
                        logger.error(
                            f"[PHASE 3] Row has incorrect column count ({len(row)}, expected 14). "
                            f"Cannot extract position data. Possible database query result corruption or schema drift."
                        )
                        raise RuntimeError(
                            f"Position row has {len(row)} columns, expected 14. "
                            f"Cannot extract position data. This may indicate database connection issues or schema mismatch."
                        ) from e
                    symbol = row[1]  # symbol is at index 1 in the row tuple
                    position_id = row[0]  # p.id is at index 0 in the row tuple
                    error_msg = str(e)
                    validation_errors.append((symbol, error_msg))
                    # Include failed position in results so orchestrator has complete visibility
                    recs.append(
                        {
                            "position_id": str(position_id),
                            "symbol": symbol,
                            "action": "FAILED_VALIDATION",
                            "error": error_msg,
                        }
                    )
                    # CRITICAL FIX: Escape error message that may contain curly braces to prevent f-string format error
                    safe_error_msg = error_msg.replace("{", "{{").replace("}", "}}")
                    logger.warning(f"  Validation failed for {symbol}: {safe_error_msg}")
                    continue

                recs.append(rec)
                self._print_recommendation(rec)
                try:
                    sp_name = f"sp_pos_{i}"
                    cursor.execute(f"SAVEPOINT {sp_name}")
                    self._persist_review(rec, cursor, i)
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    # CRITICAL FIX: Escape exception message to prevent f-string format error
                    safe_error = str(e).replace("{", "{{").replace("}", "}}")
                    logger.error(f"Failed to persist review for {rec['symbol']}: {safe_error}")
                    try:
                        cursor.execute(f"ROLLBACK TO {sp_name}")
                    except (psycopg2.DatabaseError, psycopg2.OperationalError, psycopg2.ProgrammingError) as rb_err:
                        logger.warning(
                            f"[POSITION_MONITOR] Could not rollback savepoint {sp_name}: {rb_err} - continuing"
                        )
                    continue

            # Log warning for any validation failures (included in recs as FAILED_VALIDATION)
            if validation_errors:
                logger.warning(
                    f"[WARNING] {len(validation_errors)}/{len(positions)} position(s) failed validation (included in results)"
                )

            return recs

        try:
            if cur is not None:
                return _review_with_cursor(cur)
            else:
                with DatabaseContext("write") as new_cursor:
                    return _review_with_cursor(new_cursor)
        except psycopg2.errors.GroupingError as group_err:
            # FAIL-FAST: GROUP BY errors indicate data integrity issues.
            # Cannot safely evaluate positions without proper aggregation.
            # Orchestrator is designed to halt on this exception.
            import traceback

            full_trace = traceback.format_exc()
            safe_trace = full_trace.replace("{", "{{").replace("}", "}}")
            error_msg = (
                f"[POSITION_MONITOR CRITICAL] GROUP BY error in review_positions: {group_err}\n"
                f"Full traceback: {safe_trace}"
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg) from group_err
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as db_err:
            # FAIL-FAST: Database errors in position retrieval are CRITICAL.
            # Cannot generate recommendations without position data.
            # Orchestrator is designed to halt on this exception.
            import traceback

            full_trace = traceback.format_exc()
            safe_trace = full_trace.replace("{", "{{").replace("}", "}}")
            error_msg = (
                f"[POSITION_MONITOR CRITICAL] Database error in review_positions: {db_err}\n"
                f"Full traceback: {safe_trace}"
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg) from db_err

    def _evaluate_position(  # noqa: C901
        self, row: Any, current_date: _date | datetime, cur: PsycopgCursor[Any] | None = None
    ) -> dict[str, Any]:
        try:
            (
                position_id,
                symbol,
                entry_price,
                init_stop,
                _t1_price,
                _t2_price,
                _t3_price,
                trade_date,
                _signal_date,
                quantity,
                target_hits,
                trade_ids_arr,
                current_stop,
                _db_current_price,
            ) = row
            # CRITICAL FIX: _persist_review() (below) requires rec["trade_id"], but neither
            # of this function's return paths ever supplied that key - the early stop-hit
            # return used a bogus getattr(self, 'trade_ids', None) (self.trade_ids is never
            # set anywhere, always None) and the normal return path had no trade_id key at
            # all. So _persist_review() raised KeyError('trade_id') for EVERY real position
            # review, unconditionally - review_positions() has never completed successfully
            # for any real open position. Invisible all session because there were zero real
            # open positions in this dev environment until an end-to-end synthetic
            # verification test inserted one. trade_ids_arr is a real Postgres array (the
            # SELECT above now reads the actually-populated `trade_ids_arr` column, not the
            # dead `trade_ids` varchar - see that query's comment), so take its first element
            # directly rather than splitting a comma-separated string.
            trade_id = trade_ids_arr[0] if trade_ids_arr else None
        except (ValueError, TypeError) as unpack_err:
            raise PositionValidationError(
                f"Failed to unpack position row: {type(unpack_err).__name__}: {unpack_err}. "
                f"Row has {len(row) if isinstance(row, (tuple, list)) else '?'} elements, expected 14. "
                f"This indicates database query result corruption."
            ) from unpack_err

        if entry_price is None:
            msg = f"Entry price missing for {symbol} - cannot monitor"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)
        if init_stop is None:
            msg = f"Stop loss price missing for {symbol} - cannot monitor"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)

        try:
            entry_price = float(entry_price)
        except (ValueError, TypeError) as e:
            msg = f"Invalid entry price {entry_price} for {symbol}: {e}"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg) from e

        try:
            init_stop = float(init_stop)
        except (ValueError, TypeError) as e:
            msg = f"Invalid stop price {init_stop} for {symbol}: {e}"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg) from e

        # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `<= 0` never catches NaN.
        if math.isnan(entry_price) or math.isinf(entry_price) or entry_price <= 0:
            msg = f"Invalid entry price {entry_price} for {symbol} - cannot monitor"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)
        if math.isnan(init_stop) or math.isinf(init_stop) or init_stop <= 0:
            msg = f"Invalid stop {init_stop} for {symbol} - cannot monitor"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)
        if init_stop >= entry_price:
            msg = f"Stop {init_stop} >= entry {entry_price} for {symbol} - invalid trade"
            logger.error(f"ERROR: {msg}")
            raise PositionValidationError(msg)
        active_stop = float(current_stop) if current_stop else init_stop
        if target_hits is None:
            logger.critical(
                f"CRITICAL: {symbol} - target_hits is NULL in algo_trades. "
                f"Cannot evaluate position without target hit count. "
                f"Database schema or trade data corrupted."
            )
            raise ValueError(f"Position {symbol}: target_hits missing. Cannot evaluate target progress.")
        target_hits = int(target_hits)
        # Trading-day-aware (not calendar days) so a weekend/holiday inside the hold
        # period doesn't inflate days_held past max_hold_days early - same bug class
        # fixed in algo/trading/exit_engine.py's days_held/stale_trading_days.
        _current_date_for_hold = current_date.date() if isinstance(current_date, datetime) else current_date
        days_held = MarketCalendar.trading_days_elapsed(trade_date, _current_date_for_hold)
        # FIXED 2026-08-24 (real-money-readiness goal session): exit_engine.py's identical
        # days_held computation clamps a negative result to 0 and logs a data-corruption
        # warning (trade_date in the future - e.g. a bad DB write); this call site computed
        # the same quantity but silently used the raw negative value with no warning. Harmless
        # for today's `days_held >= N` comparisons below (a negative value just never trips
        # them), but it hid a real corruption signal and diverged from the sibling fix's own
        # stated behavior. Matched here for consistency.
        if days_held < 0:
            logger.warning(
                f"{symbol}: days_held is negative ({days_held}) - data corruption detected. "
                f"Clamping to 0 for position evaluation. "
                f"trade_date={trade_date}, current_date={_current_date_for_hold}"
            )
            days_held = 0
        try:
            max_hold = int(self.config["max_hold_days"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

        # 1. Current market data
        try:
            cur_price, atr, sma_50, _ema_12 = self._fetch_current_market(symbol, current_date, cur=cur)
        except ValueError as e:
            msg = f"Position {symbol} cannot be monitored: {e}"
            logger.error(f"REJECT: {msg}")
            raise PositionValidationError(msg) from e

        # P&L (using Decimal for precision)
        risk_per_share = entry_price - init_stop
        if math.isnan(risk_per_share) or math.isinf(risk_per_share) or risk_per_share <= 0:
            raise PositionValidationError(
                f"Invalid risk per share for {symbol}: entry {entry_price} - stop {init_stop} = {risk_per_share}. "
                "Stop must be strictly below entry price."
            )
        r_multiple = (cur_price - entry_price) / risk_per_share

        # Use Decimal for monetary calculations to avoid floating point precision loss
        if quantity <= 0:
            raise PositionValidationError(f"Invalid quantity for {symbol}: {quantity} <= 0")

        price_diff = Decimal(str(cur_price)) - Decimal(str(entry_price))
        entry_price_dec = Decimal(str(entry_price))
        quantity_dec = Decimal(str(quantity))

        if entry_price_dec <= 0:
            raise PositionValidationError(f"Invalid entry price for {symbol}: {entry_price_dec} <= 0")

        unrealized_pnl = float((price_diff * quantity_dec).quantize(Decimal("0.01"), ROUND_HALF_UP))
        unrealized_pct = float((price_diff / entry_price_dec * 100).quantize(Decimal("0.01"), ROUND_HALF_UP))

        # 2. Recompute trailing stop (only ratchet UP, never down)
        proposed_stop = self._compute_trailing_stop(
            entry_price,
            active_stop,
            cur_price,
            atr,
            sma_50,
            target_hits,
        )

        if proposed_stop > cur_price:
            logger.error(f"ERROR: Proposed stop ${proposed_stop:.2f} > current price ${cur_price:.2f} for {symbol}")
            # Use Decimal for precision on stop price clamp
            proposed_stop = float(Decimal(str(cur_price)) - Decimal("0.01"))
            logger.info(f"  Clamped stop to ${proposed_stop:.2f}")

        # CRITICAL: Stop loss check MUST come first, before any other logic
        # If price <= active stop, this is a HARD EXIT condition, not optional
        if cur_price <= active_stop:
            logger.critical(
                f"[PHASE 3 CRITICAL] {symbol}: Current price ${cur_price:.2f} <= active stop ${active_stop:.2f} - IMMEDIATE EXIT REQUIRED"
            )
            # FIXED 2026-08-20 (goal: audit trade P&L / Alpaca wiring accuracy): active_stop is
            # a trailing stop that only ever ratchets UP (see _compute_trailing_stop above), so
            # once a position has run enough to hit target levels it can sit ABOVE entry_price -
            # triggering this same hard-exit condition on a pullback that still locks in a real
            # profit, not a loss. Unconditionally labeling that "STOP LOSS HIT" reads as a
            # loss-cutting event to anyone reading algo_trades.exit_reason (dashboard, trade
            # history, Slack/email notifications) even though the trade closed with a real gain -
            # live-confirmed on MRK (entry $135.97, exit $143.42, +5.48%) and CP (entry $93.92,
            # exit $98.40, +4.77%), both worded "STOP LOSS HIT" despite closing profitable.
            # Same bug class already fixed in exit_engine.py's active_stop branch on 2026-08-18
            # (live-reproduced on PDEX there) but never applied to this separate, parallel
            # "hard stop" implementation - mirrors that fix's wording split exactly.
            active_stop_dec = Decimal(str(active_stop))
            if active_stop_dec >= entry_price_dec:
                action_reason = (
                    f"Trailing stop hit: price ${cur_price:.2f} <= stop ${active_stop:.2f} "
                    f"(locked-in gain, stop raised above entry ${entry_price:.2f})"
                )
            else:
                action_reason = f"STOP LOSS HIT: price ${cur_price:.2f} <= stop ${active_stop:.2f}"

            return {
                "symbol": symbol,
                "position_id": position_id,
                "days_held": days_held,
                "quantity": quantity,
                "entry_price": entry_price,
                "current_price": cur_price,
                "r_multiple": round(r_multiple, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pct": round(unrealized_pct, 2),
                "active_stop": active_stop,
                "proposed_stop": proposed_stop,
                "target_hits": target_hits,
                "rs_label": "",
                "sector_state": "",
                "flags": ["STOP_LOSS_HIT"],
                "days_to_earnings": None,
                "action": "EARLY_EXIT",
                "action_reason": action_reason,
                "urgent_exit": True,
                "new_stop_recommended": None,
                "trade_id": trade_id,
                # In paper mode, exit_price is the final, deterministic simulated fill (never
                # reconciled against a real broker fill - see executor_exit_handler.py's
                # is_estimated_price comment). cur_price here is only as fresh as this run's
                # evaluation cycle, so a position that gapped well past active_stop between
                # checks would otherwise record that gapped price as the "fill", producing
                # phantom slippage that has nothing to do with real execution quality - the
                # exact bug exit_engine.py's own hard-capital-preservation stop path already
                # avoids via exit_price_override=stop price. Mirror that convention here so
                # both stop-exit code paths model a stop-loss fill the same way.
                "exit_price_override": active_stop,
            }

        # 3. Health flags
        flags = []

        # 3a. Relative strength vs SPY (degrading?)
        rs_state = self._check_relative_strength(symbol, current_date, cur=cur)
        if rs_state == "weakening":
            flags.append("RS_WEAKENING")
        rs_label = rs_state

        # 3b. Sector turned weak?
        sector_state = self._check_sector_health(symbol, current_date, cur=cur)
        if sector_state == "weakening":
            flags.append("SECTOR_WEAK")

        # 3c. Giving back gains (retraced from a meaningful peak)?
        # FIXED 2026-09-07 (goal: real-money-readiness audit): peak_pct > 5 was a fixed
        # percentage-of-price threshold applied uniformly regardless of the trade's own stop
        # distance (which ranges ~2%-20% across trades in live paper data). For a wide-stop
        # trade, 5% is a small fraction of its own risk unit, so this correctly stays quiet on
        # ordinary noise; for a tight-stop trade, 5% can exceed its entire initial risk, so
        # this almost never fires even after a real, R-significant favorable move reverses.
        # Live paper-trading data (Aug-Sep 2026, 130 closed trades) showed the latter in
        # practice: 73% of losing trades had a favorable peak before reversing into a full
        # loss (median peak +1.16% of price), almost all under the fixed 5% floor, so this
        # flag was structurally unable to help even flag that pattern. Normalize the trigger
        # to the trade's own risk unit (R) instead, consistent with how every other exit/
        # target rule in this system (t1/t2/t3_target_r_multiple) already measures moves in
        # R, not raw price %. 1% floor keeps this from firing on sub-1% noise for very
        # tight-stop trades. Note this only adds one candidate health flag - EARLY_EXIT still
        # requires `position_halt_flag_count` flags together (see below), so this alone does
        # not make exits more aggressive, only makes this specific flag capable of firing at
        # all for tighter-stop trades where it previously effectively never could.
        stop_distance_pct = (risk_per_share / entry_price) * 100 if entry_price > 0 else 0
        peak_trigger_pct = max(1.0, stop_distance_pct * 0.3)
        peak_pct = self._max_unrealized_pct(symbol, trade_date, current_date, entry_price, cur=cur)
        if peak_pct > peak_trigger_pct and unrealized_pct < peak_pct * 0.66:
            flags.append("GIVING_BACK_GAINS")

        # 3d. Time decay (>= half of max_hold, but no T1 hit yet)
        if days_held >= max_hold * 0.5 and target_hits == 0 and r_multiple < 0.5:
            flags.append("TIME_DECAY_NO_PROGRESS")

        # 3e. Earnings proximity (graceful degradation on data unavailability)
        # Try to fetch earnings data, but continue without it if unavailable (new IPOs may not have earnings scheduled)
        days_to_earn: int | None = None
        try:
            days_to_earn = self._days_to_earnings(symbol, current_date, cur=cur)
            if 0 <= days_to_earn <= 3:
                flags.append(f"EARNINGS_IN_{days_to_earn}D")
        except (ValueError, RuntimeError) as e:
            # Graceful degradation on earnings data unavailability
            # This is expected for new IPOs and listings without scheduled earnings
            error_msg = str(e).replace("{", "{{").replace("}", "}}")
            logger.debug(
                f"[POSITION_MONITOR] Earnings data unavailable for {symbol}: {error_msg} - continuing without earnings check"
            )

        # 3f. Distribution-day stress (graceful degradation on early-day NULL data)
        market_dist_days: int | None = None
        try:
            market_dist_days = self._fetch_market_dist_days(current_date, cur=cur)
        except (ValueError, RuntimeError) as e:
            # Graceful degradation: distribution data may be NULL early in the trading day
            # before market_exposure_daily loader has run. Continue without this check.
            error_msg = str(e).replace("{", "{{").replace("}", "}}")
            logger.debug(
                f"[POSITION_MONITOR] Market distribution data unavailable: {error_msg} - continuing without distribution check"
            )

        try:
            max_dist_days = int(self.config["max_distribution_days"])
            halt_flag_count = int(self.config["position_halt_flag_count"])
        except KeyError as e:
            raise KeyError(f"[CONFIG] Missing required field: {e}. Check algo_config table.") from e

        if market_dist_days is not None and market_dist_days > max_dist_days:
            flags.append("MARKET_DISTRIBUTION_STRESS")

        # CRITICAL DIAGNOSTIC: Log health flags to understand exit decisions
        if len(flags) > 0 or days_held >= 1:
            logger.info(
                "[POSITION_MONITOR] %s: days_held=%d, flags=%s (need %d for exit), "
                "stop=%.2f->%.2f, unrealized=%.1f%%, r_multiple=%.2f",
                symbol,
                days_held,
                flags if flags else "[]",
                halt_flag_count,
                active_stop,
                proposed_stop,
                unrealized_pct,
                r_multiple,
            )

        # Decision logic
        action = "HOLD"
        action_reason = ""
        urgent_exit = False
        new_stop_recommended = None

        if proposed_stop > active_stop:
            # Always recommend stop-raise when computed
            new_stop_recommended = proposed_stop
            action = "RAISE_STOP"
            action_reason = f"Trail stop ${active_stop:.2f} -> ${proposed_stop:.2f}"

        if len(flags) >= halt_flag_count:
            action = "EARLY_EXIT"
            action_reason = f"{len(flags)} health flags: {', '.join(flags)}"
            urgent_exit = True

        # Special case: earnings within 1-2 days = always exit
        if days_to_earn is not None and 0 <= days_to_earn <= 2:
            action = "EARLY_EXIT"
            action_reason = f"Earnings in {days_to_earn} day(s) - flatten before report"
            urgent_exit = True

        return {
            "symbol": symbol,
            "position_id": str(position_id),
            "days_held": days_held,
            "quantity": quantity,
            "entry_price": entry_price,
            "current_price": cur_price,
            "r_multiple": round(r_multiple, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pct": round(unrealized_pct, 2),
            "active_stop": active_stop,
            "proposed_stop": proposed_stop,
            "target_hits": target_hits,
            "rs_label": rs_label,
            "sector_state": sector_state,
            "flags": flags,
            "days_to_earnings": days_to_earn,
            "action": action,
            "action_reason": action_reason,
            "urgent_exit": urgent_exit,
            "new_stop_recommended": new_stop_recommended,
            "trade_id": trade_id,
        }


if __name__ == "__main__":
    from algo.infrastructure import get_config

    monitor = PositionMonitor(get_config())
    monitor.review_positions()
