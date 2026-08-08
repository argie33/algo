#!/usr/bin/env python3
from __future__ import annotations

import logging
import time
import uuid
from datetime import date as _date
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, cast

import psycopg2
import requests
from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure import get_alpaca_timeout
from algo.infrastructure.config.sql_intervals import get_interval_sql
from algo.infrastructure.market_calendar import MarketCalendar
from algo.signals import SignalComputer
from algo.trading import TradeExecutor
from algo.trading.exceptions import DatabaseError, ExchangeAPIError
from algo.config.api_endpoints import get_alpaca_data_url
from algo.config.credential_manager import get_alpaca_credentials
from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ
from utils.trading import PositionStatus, TradeStatus

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

"""
Exit Engine - Monitor positions and execute exits (HARDENED)

Exit hierarchy (checked in order):

1. STOP     - current price <= active stop (initial or trailed)

2. MINERVINI BREAK  - close < 21-EMA on volume > 50d avg (or close < 50-DMA cleanly)

3. TIME     - held >= max_hold_days

4. T3       - price >= target_3 (4R) '' exit final 25%

5. T2       - price >= target_2 (3R) '' exit 25% on pullback, raise stop to T1 area

6. T1       - price >= target_1 (1.5R) '' exit 50% on pullback, raise stop to entry (breakeven)

7. CHANDELIER TRAIL  - 3xATR from highest high (or 21-EMA after 10d)

8. TD SEQUENTIAL  - 9-count (50%) or 13-count (100%) exhaustion

9. FIRST RED DAY  - after 2.5R+ gain, first big down day on heavy volume '' exit 50%

10. CLIMAX RUN EXHAUSTION  - 30+ days, 5R+ gain, 20%+ in last 10d '' exit 50%

11. DISTRIBUTION  - market distribution day count exceeds limit (config-gated)

State tracked on algo_positions:

  - target_levels_hit (0/1/2/3): which T-levels have already triggered

  - current_stop_price: trailed stop after T1/T2 hits
"""

logger = logging.getLogger(__name__)


class PositionContext:
    """Context for position exit evaluation with integrated check methods."""

    def __init__(
        self,
        symbol: str,
        current_date: _date,
        cur_price: Decimal,
        prev_close: Decimal | None,
        entry_price: Decimal,
        active_stop: Decimal,
        init_stop: Decimal,
        t1_price: Decimal | None,
        t2_price: Decimal | None,
        t3_price: Decimal | None,
        target_hits: int,
        days_held: int,
        dist_days_today: int | None,
        config: AlgoConfig | dict[str, Any],
        cur: PsycopgCursor[Any] | None = None,
        t1_hit_time: datetime | None = None,
        t2_hit_time: datetime | None = None,
        t3_hit_time: datetime | None = None,
        last_partial_exit_date: _date | None = None,
        partial_exits_log: str | None = None,
    ) -> None:
        self.symbol = symbol
        self.current_date = current_date
        self.cur_price = cur_price
        self.prev_close = prev_close
        self.entry_price = entry_price
        self.active_stop = active_stop
        self.init_stop = init_stop
        if t1_price is None or t2_price is None or t3_price is None:
            missing = [f"T{i}" for i, p in enumerate([t1_price, t2_price, t3_price], 1) if p is None]
            raise ValueError(
                f"CRITICAL: {symbol} position loaded without target prices: {', '.join(missing)}. "
                "Cannot execute position without exit plan."
            )
        self.t1_price = t1_price
        self.t2_price = t2_price
        self.t3_price = t3_price
        self.target_hits = target_hits
        self.days_held = days_held
        self.dist_days_today = dist_days_today
        self.t1_hit_time = t1_hit_time
        self.t2_hit_time = t2_hit_time
        self.t3_hit_time = t3_hit_time
        self.last_partial_exit_date = last_partial_exit_date
        self.partial_exits_log = partial_exits_log
        self.config = config
        self.cur = cur
        self._validate_exit_config()

    def _validate_exit_config(self) -> None:
        """Validate critical exit rule config keys are present at initialization.

        Only validates fields that are actually used in this position's exit checks.
        Fail-fast on missing required config rather than during individual rule checks.
        """
        # Minimal required config - fields used by all exit checks
        required_config_keys = {
            "exit_on_rs_line_break_50dma": bool,
            "max_hold_days": int,
            "eight_week_rule_threshold_pct": float,
            "eight_week_rule_window_days": int,
        }

        # Optional fields - only checked if actually used in exit chain
        optional_config_keys = {
            "min_sqs_for_exit": float,
            "max_risk_per_trade_pct": float,
        }

        missing_keys = []
        for key, expected_type in required_config_keys.items():
            if key not in self.config:
                missing_keys.append(f"'{key}' ({expected_type.__name__})")
            elif not isinstance(self.config[key], expected_type):
                actual_type = type(self.config[key]).__name__
                missing_keys.append(
                    f"'{key}' has type {actual_type}, expected {expected_type.__name__}"
                )

        if missing_keys:
            raise ValueError(
                f"[{self.symbol}] CRITICAL: Exit rule config incomplete. Missing: {', '.join(missing_keys)}. "
                f"Position cannot be monitored without complete exit parameters. "
                f"Check orchestrator config validation."
            )

    def check_stop_loss(self) -> tuple[bool, dict[str, Any] | None]:
        """Stop loss check: hard capital preservation rule."""
        if self.cur_price <= self.active_stop:
            return (
                True,
                {
                    "stage": "stop",
                    "fraction": 1.0,
                    "reason": f"STOP hit: ${float(self.cur_price):.2f} <= ${float(self.active_stop):.2f}",
                },
            )
        return False, None

    def check_minervini_break(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Minervini break: DISABLED (0% win rate in backtest 2026-08-05).

        This exit was disabled due to poor performance. Keeping method signature for
        backwards compatibility but always returns False (exit disabled).
        To re-enable: add exit_on_minervini_break=true to algo_config.
        """
        return False, None

    def check_rs_line_break(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """RS line break: relative strength deterioration vs SPY.

        TUNING FIX (2026-08-02): Only exit on RS line breaks if position is a LOSER.
        Winners were being exited when sector weakened, destroying profits.
        Now: RS line break only exits positions with R <= 0.5 (losers only).
        """
        if "exit_on_rs_line_break_50dma" not in self.config:
            raise ValueError(
                "CRITICAL: 'exit_on_rs_line_break_50dma' config missing. "
                "Cannot proceed with exit rules  - risk controls undefined."
            )
        if self.config["exit_on_rs_line_break_50dma"]:
            if engine._rs_line_breaking(self.cur, self.symbol, self.current_date):
                # TUNING FIX: Calculate current R-multiple to check if position is a loser
                # R = (current_price - entry_price) / (entry_price - stop_loss)
                # Only exit if R <= 0.5 (loser), never exit winners when sector weakens
                risk_per_share = self.entry_price - self.init_stop
                if risk_per_share <= 0:
                    logger.warning(f"[EXIT] {self.symbol}: RS line break check skipped - invalid risk_per_share")
                    return False, None

                current_r = (self.cur_price - self.entry_price) / risk_per_share
                if current_r <= 0.5:
                    # LOSER: Sector weakness + down money = exit cleanly
                    return (
                        True,
                        {
                            "stage": "stop",
                            "fraction": 1.0,
                            "reason": f"RS line broke below 50-DMA (loser: R={float(current_r):.2f})",
                        },
                    )
                else:
                    # WINNER: Sector weakness but position profitable - DO NOT EXIT
                    logger.debug(
                        f"[EXIT] {self.symbol}: RS line break ignored (winner: R={float(current_r):.2f}, "
                        f"price=${float(self.cur_price):.2f}, entry=${float(self.entry_price):.2f})"
                    )
                    return False, None
        return False, None

    def check_time_exit(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Time-based exit with O'Neil 8-week rule override.

        CRITICAL FIX SESSION 41: Time-based exits are discretionary (not capital preservation),
        so they respect min_hold_days gate. This prevents same-day time exits while still allowing
        hard stops, targets, and distribution exits that reduce exposure immediately.
        """
        min_hold_val = self.config.get("min_hold_days")
        if min_hold_val is None:
            raise ValueError("CRITICAL: min_hold_days config missing. Cannot enforce minimum holding period.")

        min_hold_days = int(min_hold_val)
        # CRITICAL FIX: Clamp negative days_held to 0 (data corruption safeguard)
        # Negative values block all exits - treat same-day entries as 0 days, not negative
        days_held_for_check = max(0, self.days_held)
        if days_held_for_check < min_hold_days:
            return False, None

        max_hold_val = self.config.get("max_hold_days")
        if max_hold_val is None:
            raise ValueError("CRITICAL: max_hold_days config missing. Cannot enforce maximum holding period.")

        max_hold = int(max_hold_val)
        if self.days_held >= max_hold:
            eight_wk_val = self.config.get("eight_week_rule_threshold_pct")
            if eight_wk_val is None:
                raise ValueError("CRITICAL: eight_week_rule_threshold_pct config missing.")

            eight_wk_threshold = float(eight_wk_val)
            eight_wk_window_val = self.config.get("eight_week_rule_window_days")
            if eight_wk_window_val is None:
                raise ValueError("CRITICAL: eight_week_rule_window_days config missing.")

            eight_wk_window = int(eight_wk_window_val)
            eight_wk_ext = engine._eight_week_rule_active(
                self.cur,
                self.symbol,
                self.current_date,
                float(self.entry_price),
                self.days_held,
                eight_wk_threshold,
                eight_wk_window,
            )

            if eight_wk_ext and self.days_held < 56:
                return False, None

            return (
                True,
                {
                    "stage": "time",
                    "fraction": 1.0,
                    "reason": f"TIME exit: {self.days_held} days >= {max_hold} max",
                },
            )
        return False, None

    def _was_target_hit_today(self, hit_time: datetime | None) -> bool:
        if hit_time is None:
            return False
        hit_date = hit_time.date() if isinstance(hit_time, datetime) else hit_time
        return hit_date == self.current_date

    def _was_distribution_reduced_today(self) -> bool:
        """Guard against check_distribution firing repeatedly on every exit-engine pass
        while dist_days_today stays above max_dd, which - unlike the T1/T2/T3 checks - has no
        per-day dedup of its own. Confirmed live 2026-07-27: 7 positions were each reduced by
        50% THREE separate times in the same single day (all three logged under the same
        last_partial_exit_date), compounding down to ~12.5% of their original size from one
        ongoing market condition instead of a single one-time de-risking action."""
        if self.last_partial_exit_date is None or self.partial_exits_log is None:
            return False
        last_exit_date = (
            self.last_partial_exit_date.date()
            if isinstance(self.last_partial_exit_date, datetime)
            else self.last_partial_exit_date
        )
        if last_exit_date != self.current_date:
            return False
        last_log_entry = self.partial_exits_log.rsplit("; ", 1)[-1]
        return "Market distribution" in last_log_entry

    def check_target_t1(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """T1 target exit (1.5R): 50% position reduction."""
        if self.target_hits == 0 and self.cur_price >= self.t1_price:
            if self._was_target_hit_today(self.t1_hit_time):
                return False, None
            if "require_target_pullback" not in self.config:
                raise ValueError(
                    "Exit engine config missing 'require_target_pullback' flag. "
                    "Cannot proceed with target exits without explicit configuration."
                )
            require_pb = bool(self.config["require_target_pullback"])
            if not require_pb or engine._is_pulling_back(self.cur, self.symbol, self.current_date):
                return (
                    True,
                    {
                        "stage": "target_1",
                        "fraction": 0.50,
                        "reason": f"T1 exit: ${float(self.cur_price):.2f} >= ${float(self.t1_price):.2f} (1.5R)",
                        "new_stop": float(max(self.active_stop, self.entry_price)),
                    },
                )
        return False, None

    def check_target_t2(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """T2 target exit (3R): 25% position reduction with stop raise to T1."""
        if self.target_hits == 1 and self.cur_price >= self.t2_price:
            if self._was_target_hit_today(self.t2_hit_time):
                return False, None
            if "require_target_pullback" not in self.config:
                raise ValueError(
                    "Exit engine config missing 'require_target_pullback' flag. "
                    "Cannot proceed with target exits without explicit configuration."
                )
            require_pb = bool(self.config["require_target_pullback"])
            if not require_pb or engine._is_pulling_back(self.cur, self.symbol, self.current_date):
                stop_for_t2 = max(self.active_stop, self.t1_price)
                return (
                    True,
                    {
                        "stage": "target_2",
                        "fraction": 0.50,
                        "reason": f"T2 exit: ${float(self.cur_price):.2f} >= ${float(self.t2_price):.2f} (3R)",
                        "new_stop": float(stop_for_t2),
                    },
                )
        return False, None

    def check_target_t3(self) -> tuple[bool, dict[str, Any] | None]:
        """T3 target exit (4R): final 25% position reduction."""
        if self.target_hits == 2 and self.cur_price >= self.t3_price:
            if not self._was_target_hit_today(self.t3_hit_time):
                return (
                    True,
                    {
                        "stage": "target_3",
                        "fraction": 1.0,
                        "reason": f"T3 target hit: ${float(self.cur_price):.2f} >= ${float(self.t3_price):.2f} (4R) - FINAL EXIT",
                    },
                )
        return False, None

    def check_chandelier_trail(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Chandelier/EMA trailing stop: tightens stop after 1R profit."""
        risk_per_share = self.entry_price - self.init_stop
        r_mult = (
            ((Decimal(str(self.cur_price)) - self.entry_price) / risk_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if risk_per_share > 0
            else Decimal(0)
        )

        chandelier_enabled = self.config.get("use_chandelier_trail")
        if chandelier_enabled is None:
            raise ValueError("CRITICAL: use_chandelier_trail config missing.")

        if bool(chandelier_enabled) and r_mult >= Decimal(1):
            chand_stop = engine._chandelier_or_ema_stop(self.cur, self.symbol, self.current_date, self.days_held)
            if chand_stop and Decimal(str(chand_stop)) > self.active_stop:
                return (
                    True,
                    {
                        "stage": "raise_stop_trail",
                        "fraction": 0.0,
                        "reason": f"Chandelier/EMA trail tightens stop to ${chand_stop:.2f}",
                        "new_stop": chand_stop,
                    },
                )
        return False, None

    def check_td_sequential(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """TD Sequential exhaustion: 9-count (50%) or 13-count (100%) exit."""
        risk_per_share = self.entry_price - self.init_stop
        r_mult = (
            ((Decimal(str(self.cur_price)) - self.entry_price) / risk_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if risk_per_share > 0
            else Decimal(0)
        )

        td_seq_enabled = self.config.get("exit_on_td_sequential")
        if td_seq_enabled is None:
            raise ValueError("CRITICAL: exit_on_td_sequential config missing.")

        if bool(td_seq_enabled) and self.target_hits >= 1:
            if r_mult >= Decimal("0.5"):
                td_state = engine._get_td_state(self.cur, self.symbol, self.current_date)
                # FAIL-FAST: Validate critical TD Sequential fields present before using
                required_fields = ["combo_13_complete", "completed_9", "setup_type"]
                missing = [f for f in required_fields if f not in td_state]
                if missing:
                    raise ValueError(
                        f"[TD_SEQUENTIAL] {self.symbol}: TD state missing critical fields {missing}. "
                        f"Cannot make exit decision without complete TD data. Available: {list(td_state.keys())}"
                    )
                if td_state["combo_13_complete"] and td_state["setup_type"] == "sell":
                    return (
                        True,
                        {
                            "stage": "td_combo_13",
                            "fraction": 1.0,
                            "reason": f"TD Combo 13-count exhaustion (FULL EXIT, R={float(r_mult):.2f})",
                        },
                    )
                if td_state["completed_9"] and td_state["setup_type"] == "sell":
                    return (
                        True,
                        {
                            "stage": "td_exhaustion",
                            "fraction": 0.50,
                            "reason": f"TD Sequential 9-count exhaustion (R={float(r_mult):.2f})",
                            "new_stop": float(max(self.active_stop, self.entry_price)),
                        },
                    )
        return False, None

    def check_first_red_day(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """First red day: institutional distribution after parabolic run."""
        risk_per_share = self.entry_price - self.init_stop
        r_mult = (
            ((Decimal(str(self.cur_price)) - self.entry_price) / risk_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if risk_per_share > 0
            else Decimal(0)
        )

        if r_mult >= Decimal("2.5") and self.prev_close is not None and self.prev_close > 0:
            down_pct = float(
                (
                    (Decimal(str(self.prev_close)) - Decimal(str(self.cur_price)))
                    / Decimal(str(self.prev_close))
                    * Decimal(100)
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            if down_pct >= 1.5:
                vol_check = engine._check_volume_spike(self.cur, self.symbol, self.current_date, 1.5)
                if vol_check:
                    return (
                        True,
                        {
                            "stage": "first_red_day",
                            "fraction": 0.50,
                            "reason": f"First Red Day: down {down_pct:.2f}% on heavy volume (R={float(r_mult):.2f})",
                            "new_stop": float(max(self.active_stop, self.entry_price)),
                        },
                    )
        return False, None

    def check_climax_exhaustion(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Climax run exhaustion: parabolic move climax after 5R+ gain in 10d."""
        risk_per_share = self.entry_price - self.init_stop
        r_mult = (
            ((Decimal(str(self.cur_price)) - self.entry_price) / risk_per_share).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if risk_per_share > 0
            else Decimal(0)
        )

        if self.days_held > 30 and r_mult >= Decimal("5.0"):
            gain_10d = engine._compute_gain_last_n_days(self.cur, self.symbol, self.current_date, 10)
            if gain_10d is not None and gain_10d >= 20.0:
                return (
                    True,
                    {
                        "stage": "climax_exhaustion",
                        "fraction": 0.50,
                        "reason": f"Climax run exhaustion: gained {gain_10d:.1f}% in last 10d (R={float(r_mult):.2f})",
                        "new_stop": float(max(self.active_stop, self.entry_price)),
                    },
                )
        return False, None

    def check_distribution(self) -> tuple[bool, dict[str, Any] | None]:
        """Distribution day: market distribution day count exceeded."""
        dist_enabled = self.config.get("exit_on_distribution_day")
        if dist_enabled is None:
            raise ValueError("CRITICAL: exit_on_distribution_day config missing.")

        if bool(dist_enabled) and self.dist_days_today is not None:
            max_dd_val = self.config.get("max_distribution_days")
            if max_dd_val is None:
                raise ValueError("CRITICAL: max_distribution_days config missing.")

            max_dd = int(max_dd_val)
            if self.dist_days_today > max_dd and not self._was_distribution_reduced_today():
                # CRITICAL FIX: Prevent stop from being raised above current price for underwater positions
                # The bug (2026-07-27): check_distribution() raised stop to entry_price even for positions
                # below entry_price, guaranteeing stop-out on the next pass (underwater positions would exit
                # 50% AND immediately stop-out the remaining half, cascading into circuit breaker halt).
                # Distribution market conditions justify reducing exposure (50% exit), but we must ensure
                # the protective stop does NOT go above the current price (which would guarantee immediate stop-out).
                at_or_above_breakeven = self.cur_price >= self.entry_price
                if at_or_above_breakeven:
                    # Position is at or above breakeven - safe to raise stop to entry price to lock in gains
                    new_stop = max(self.active_stop, self.entry_price)
                    reason = f"Market distribution: {self.dist_days_today} dist days > {max_dd}  - reducing 50% of profitable position, stop raised to breakeven"
                else:
                    # Position is underwater - reduce exposure but keep stop at current level
                    # to avoid creating a guaranteed stop-out on the remaining half
                    new_stop = self.active_stop
                    reason = f"Market distribution: {self.dist_days_today} dist days > {max_dd}  - reducing 50% of position to manage market distribution risk (stop stays at {float(self.active_stop):.2f})"

                return (
                    True,
                    {
                        "stage": "distribution",
                        "fraction": 0.5,
                        "new_stop": new_stop,
                        "reason": reason,
                    },
                )
        return False, None


def _persist_exit_check_error(
    error_date: _date,
    trade_id: Any,
    position_id: Any,
    symbol: str,
    error_type: str,
    error_message: str,
) -> None:
    """Best-effort audit write for a failed exit check, on its own connection.

    2026-08-03: two live runs (LOCAL-AFTERNOON-...-100833, ...-101518) each recorded real
    trade_errors in orchestrator_execution_log with zero corresponding rows in
    algo_exit_check_errors for that date - the alert's "see algo_exit_check_errors for
    detail" pointer was a dead end. A same-day mitigation upgraded the failure-path
    logging to CRITICAL with pgcode/pgerror/diag/traceback, but the underlying INSERT
    still ran as a nested SAVEPOINT on the *same* connection/transaction that had just
    failed - direct DB reproduction that day ruled out a broken INSERT statement, a
    full-batch rollback, and a plain SERIALIZABLE conflict as causes, without finding the
    real one. Rather than keep guessing at what state the shared connection could be in,
    this now writes the audit row on a brand-new DatabaseContext connection, decoupling
    audit-trail durability from whatever happened to the main exit-check transaction -
    whatever the original failure mode was, it cannot also break an unrelated connection.
    """
    try:
        with DatabaseContext("write") as audit_cur:
            audit_cur.execute(
                """INSERT INTO algo_exit_check_errors
                   (error_date, trade_id, position_id, symbol, error_type, error_message)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (error_date, trade_id, position_id, symbol, error_type, error_message[:2000]),
            )
    except Exception as audit_err:
        diag_detail = ""
        if isinstance(audit_err, psycopg2.Error):
            diag_detail = (
                f" pgcode={getattr(audit_err, 'pgcode', None)} "
                f"pgerror={getattr(audit_err, 'pgerror', None)} "
                f"diag={getattr(getattr(audit_err, 'diag', None), 'message_detail', None)}"
            )
        logger.critical(
            f"[AUDIT] Failed to persist exit-check error for {symbol} (trade {trade_id}, "
            f"error_type={error_type}) to algo_exit_check_errors on an isolated connection: "
            f"{type(audit_err).__name__}: {audit_err}.{diag_detail} "
            f"algo_exit_check_errors will NOT have a row for this failure. "
            f"Original error: {error_message}",
            exc_info=audit_err,
        )


class ExitEngine:
    """Monitor and execute position exits."""

    def __init__(self, config: AlgoConfig | dict[str, Any]) -> None:

        self._validate_config(config)
        self.config = config

        self.executor = TradeExecutor(config)

        self.verbose = True

    def _validate_config(self, config: AlgoConfig | dict[str, Any]) -> None:
        """Validate required configuration keys exist (fail-fast at init time).

        Raises:
            ValueError: If required config keys are missing
        """
        required_keys = [
            "min_hold_days",
            "max_hold_days",
            "eight_week_rule_threshold_pct",
            "eight_week_rule_window_days",
            "exit_on_distribution_day",
            "max_distribution_days",
            "move_be_at_r",
            "chandelier_atr_mult",
        ]
        missing = [k for k in required_keys if k not in config]
        if missing:
            raise ValueError(
                f"ExitEngine config missing required keys: {missing}. "
                f"Cannot initialize exit engine without these values."
            )

    def check_and_execute_exits(self, current_date: _date | None = None) -> tuple[int, int, int, int]:
        """Evaluate all open positions for exit/stop-raise conditions.

        Returns:
            (exits_executed, stop_raises_executed, trade_errors) - exits_executed only
            counts positions actually closed or partially closed (fraction > 0, plus the
            delisted/no-price-data forced closes below); a stop-raise-only outcome
            (fraction == 0 - no shares sold, just a tighter stop) is counted separately
            in stop_raises_executed. Previously both were folded into a single count, so
            phase6_exit_execution.py's summary line ("N exits, M stop-raises") could read
            e.g. "16 exits, 0 stop-raises" when in fact 0 positions closed and all 16 were
            stop-raise-only - confirmed live 2026-07-27 (all 16 pre-existing positions
            were still open and at their original quantity after a run reporting 16
            "exits"). trade_errors counts per-trade exceptions caught and swallowed below
            (savepoint rolled back, position left for the next run to re-evaluate).
            Callers MUST surface this, not just exits_executed: a trade that errors here
            got no exit/stop check at all this run, which is a real gap in position risk
            coverage even though it isn't visible as an exception (see
            phase6_exit_execution.py caller).
        """

        if current_date is None:
            # CRITICAL: Use ET (Eastern Time) for all trading dates, not UTC
            # Market hours are 9:30 AM - 4:00 PM ET, not UTC
            current_date = datetime.now(EASTERN_TZ).date()

        with DatabaseContext("write") as cur:
            try:
                # Initialize error counters FIRST, before any code that might raise
                exits_executed = 0
                stop_raises_executed = 0
                trade_errors = 0
                forced_closes_no_price = 0

                # CRITICAL FIX Session 391: Use SERIALIZABLE isolation to prevent phantom reads
                # between FOR UPDATE lock and position update. This ensures consistency
                # when position data is read in multiple places (exit_engine, exit_handler, position_tracker)
                cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")

                logger.info(f"\n{'=' * 70}")

                logger.info(f"EXIT ENGINE CHECK - {current_date}")

                logger.info(f"{'=' * 70}\n")

                # CRITICAL FIX Session 392: Wrap initial position fetch in try-except
                # If the initial SELECT fails (e.g., constraint violation, data corruption),
                # the transaction becomes aborted. All subsequent queries return "current
                # transaction is aborted" errors. Catch database errors early and fail
                # cleanly rather than letting subsequent per-position loop queries fail
                # with confusing transaction abort messages.
                try:
                    # CRITICAL FIX: This WHERE clause previously hardcoded
                    # `t.status IN ('open', 'pending')` instead of calling TradeStatus.all_open().
                    # A real live (execution_mode=auto) filled order writes algo_trades.status =
                    # 'filled' or 'partially_filled' literally (see executor_entry_handler.py) -
                    # never 'open'/'pending', those are paper-mode/review-mode-only values. That
                    # meant this, the core exit-candidate query for the whole exit engine, would
                    # never select a live-filled position for stop-loss/target/time-based exit
                    # evaluation - the position would sit with no automated exit coverage
                    # indefinitely. Invisible in every prior run because every trade so far has
                    # been paper mode (status='open'). Now selects every non-terminal status.
                    open_trade_statuses = TradeStatus.all_open()
                    status_placeholders = ", ".join(["%s"] * len(open_trade_statuses))
                    # CRITICAL FIX: Add FOR UPDATE to initial position fetch to prevent TOCTOU race
                    # If we fetch positions without lock, another transaction can modify them in the gap
                    # between this SELECT and the FOR UPDATE recheck at line 625. This causes duplicate
                    # exits or exits on wrong positions under concurrent load. Lock positions here.
                    cur.execute(
                        f"""SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,
                                  t.target_1_price, t.target_2_price, t.target_3_price,
                                  t.trade_date,
                                  p.position_id, p.quantity, p.target_levels_hit,
                                  p.current_stop_price, p.target_1_hit_time, p.target_2_hit_time, p.target_3_hit_time,
                                  t.last_partial_exit_date, t.partial_exits_log
                           FROM algo_trades t
                           JOIN algo_positions p ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
                           WHERE t.status IN ({status_placeholders}) AND p.status = %s AND p.quantity > 0
                           ORDER BY t.trade_date ASC
                           FOR UPDATE OF p""",
                        (*open_trade_statuses, PositionStatus.OPEN.value),
                    )

                    trades = cur.fetchall()

                    if not trades:
                        logger.info("No open positions.\n")

                        return 0, 0, 0, 0

                    # Cache market distribution-day status once for the run

                    dist_days_today = self._fetch_market_dist_days(cur, current_date)
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as _init_err:
                    logger.critical(
                        f"[EXIT_ENGINE CRITICAL] Initial position fetch failed: {type(_init_err).__name__}: {_init_err}. "
                        f"Cannot proceed with exit evaluation. This indicates a database connectivity or schema issue."
                    )
                    raise DatabaseError(f"Exit engine initialization failed: {_init_err}") from _init_err

                for _idx, row in enumerate(trades):
                    (
                        trade_id,
                        symbol,
                        entry_price,
                        init_stop,
                        t1_price,
                        t2_price,
                        t3_price,
                        trade_date,
                        _position_id,
                        _quantity,
                        target_hits,
                        current_stop,
                        t1_hit_time,
                        t2_hit_time,
                        t3_hit_time,
                        last_partial_exit_date,
                        partial_exits_log,
                    ) = row

                    # ISSUE 11 FIX: Use unique savepoint names to prevent collision on retry
                    _sp = f"sp_exit_{int(time.time()*1000000)}_{uuid.uuid4().hex[:8]}"
                    cur.execute(f"SAVEPOINT {_sp}")
                    is_estimated_price_exit = False  # Reset for each position - used if archive price fallback
                    try:
                        # Issue #22: Lock position row to prevent concurrent exits (TOCTOU race)
                        # CRITICAL FIX Session 391: Re-fetch position quantity after FOR UPDATE lock
                        # to ensure we have fresh data (Phase 3 may have modified it before Phase 6)

                        cur.execute(
                            "SELECT status, quantity, current_stop_price FROM algo_positions WHERE position_id = %s FOR UPDATE",
                            (_position_id,),
                        )

                        status_row = cur.fetchone()

                        if not status_row:
                            logger.critical(
                                f"[EXIT_ENGINE CRITICAL] {symbol} ({_position_id}): Position loaded in initial query "
                                f"but NOT FOUND in status recheck during exit evaluation. This indicates DATA INTEGRITY FAILURE "
                                f"(position missing from database during transaction, or position_id corrupted). "
                                f"Cannot proceed with exit evaluation - halting to prevent silent data loss."
                            )
                            raise RuntimeError(
                                f"Position data integrity failure for {symbol} ({_position_id}): "
                                f"loaded initially but missing during exit check. Database corruption or concurrent deletion suspected. "
                                f"Exit engine MUST halt until data integrity verified."
                            )

                        status, fresh_quantity, fresh_stop_price = status_row

                        # CRITICAL FIX Session 20: Hard stop loss check MUST use t.stop_loss_price from trade record
                        # NOT current_stop_price from position (which is a trailing/running stop that gets updated)
                        # The hard stop loss is the initial capital preservation level set at entry time

                        if status != "open":
                            logger.debug(f"Position {symbol} already closed, skipping exit check")
                            cur.execute(f"RELEASE SAVEPOINT {_sp}")
                            continue

                        # CRITICAL: Detect quantity mismatch (Phase 3 modified position after our initial read)
                        if fresh_quantity != _quantity:
                            logger.warning(
                                f"[EXIT_ENGINE] {symbol}: Position quantity changed since initial read "
                                f"(_quantity={_quantity} vs fresh_quantity={fresh_quantity}). "
                                f"This indicates Phase 3 modified the position. Using fresh quantity for exit calculation."
                            )

                        if fresh_quantity <= 0:
                            logger.debug(
                                f"[EXIT_ENGINE] {symbol}: Position quantity is now {fresh_quantity}, "
                                f"position was fully closed by Phase 3. Skipping exit evaluation."
                            )
                            cur.execute(f"RELEASE SAVEPOINT {_sp}")
                            continue

                        # Use fresh stop price if available (ensures exit calculation has latest data)
                        effective_current_stop = fresh_stop_price if fresh_stop_price else current_stop

                        try:
                            entry_price = Decimal(str(entry_price))

                            init_stop = Decimal(str(init_stop))

                            active_stop = Decimal(str(effective_current_stop)) if effective_current_stop else init_stop

                            t1_price = Decimal(str(t1_price)) if t1_price else None

                            t2_price = Decimal(str(t2_price)) if t2_price else None

                            t3_price = Decimal(str(t3_price)) if t3_price else None

                            if target_hits is None:
                                raise ValueError(
                                    f"{symbol}: target_hits is NULL in database  - data corruption detected"
                                )

                            target_hits = int(target_hits)

                        except (TypeError, ValueError) as e:
                            raise ValueError(
                                f"Cannot evaluate exit checks for {symbol}: invalid price data  - {e}"
                            ) from e

                        try:
                            cur_price, prev_close = self._fetch_recent_prices(cur, symbol, current_date)
                        except RuntimeError as fetch_err:
                            # Only reach here in auto mode when symbol is truly missing from both
                            # Alpaca AND our database. In paper/dry modes, _fetch_alpaca_quote returns None
                            # instead of raising, so _fetch_recent_prices handles it via database fallback.
                            if "unavailable" in str(fetch_err).lower() or "404" in str(fetch_err).lower():
                                execution_mode = self.config.get("execution_mode", "paper")
                                error_context = (
                                    f"live trading (symbol delisted or permission lost)"
                                    if execution_mode == "auto"
                                    else f"{execution_mode} mode (sandbox limitation despite DB prices)"
                                )
                                logger.critical(
                                    f"[EXIT ENGINE CRITICAL] {symbol}: Symbol unavailable in {error_context}. "
                                    f"Cannot exit position without current price data. Will mark for manual review. Error: {fetch_err}"
                                )
                                # CRITICAL FIX: Do NOT fall back to entry_price for exit_price
                                # Using entry_price masks the actual exit value and produces false P&L
                                # (e.g., position that sold at $5 will show as break-even if bought at $100)
                                # Mark position as requiring manual exit price determination
                                #
                                # CRITICAL FIX: this close-out UPDATE previously hardcoded
                                # `status = 'open'`, but the SELECT above that surfaces exit
                                # candidates was widened to TradeStatus.all_open() (covers live
                                # 'filled'/'partially_filled' trades too - see the fix at the top of
                                # this method). A live trade selected with status='filled' would
                                # never match this UPDATE's WHERE clause, so it would silently stay
                                # 'filled' forever - counted in exits_executed but never actually
                                # closed. Use the same status set on both tables so a trade this
                                # method selects is always one it can also close.
                                # SEPARATE BUG, fixed alongside the status widening above:
                                # PostgreSQL does not support ORDER BY/LIMIT directly on an UPDATE
                                # statement - this raised a bare `psycopg2.errors.SyntaxError: syntax error at or near "ORDER"`
                                # every time this branch was reached (confirmed live against this
                                # DB), meaning a delisted/unavailable symbol crashed the exit loop
                                # instead of being gracefully marked for manual review. Rewritten to
                                # target the most-recent matching trade_id via a subquery.
                                open_trade_statuses_close = TradeStatus.all_open()
                                trade_status_placeholders = ", ".join(["%s"] * len(open_trade_statuses_close))
                                # CRITICAL FIX: For delisted/unavailable symbols, close position with NULL P&L
                                # Do NOT calculate fake P&L when price is unavailable (no fallback to entry_price)
                                # Set estimated_exit_price to current_price to mark as pending-reconciliation
                                # (not corrupt) so Phase 9 reconciliation can handle it gracefully
                                cur.execute(
                                    f"""UPDATE algo_trades SET status = 'closed', exit_date = %s,
                                       exit_time = CURRENT_TIMESTAMP,
                                       exit_price = NULL,
                                       estimated_exit_price = %s,
                                       profit_loss_dollars = NULL,
                                       profit_loss_pct = NULL,
                                       exit_reason = %s, updated_at = CURRENT_TIMESTAMP
                                       WHERE trade_id = %s AND status IN ({trade_status_placeholders})""",
                                    (
                                        current_date,
                                        cur_price if cur_price and cur_price > 0 else None,
                                        "delisted_or_unavailable|price_data_missing",
                                        trade_id,
                                        *open_trade_statuses_close,
                                    ),
                                )
                                open_position_statuses_close = PositionStatus.all_active()
                                position_status_placeholders = ", ".join(["%s"] * len(open_position_statuses_close))
                                # CRITICAL FIX: For delisted/unavailable symbols, close position with NULL P&L
                                # Do NOT calculate fake P&L when price is unavailable (no fallback to entry_price)
                                # Leave current_price and profit_loss fields as NULL to indicate manual review needed
                                cur.execute(
                                    f"""UPDATE algo_positions SET status = 'closed', closed_at = CURRENT_TIMESTAMP,
                                       exit_reason = %s,
                                       current_price = NULL,
                                       profit_loss_dollars = NULL,
                                       unrealized_pnl_pct = NULL,
                                       unrealized_pnl = NULL,
                                       updated_at = CURRENT_TIMESTAMP
                                       WHERE position_id = %s AND status IN ({position_status_placeholders})""",
                                    (
                                        "delisted_or_unavailable|price_data_missing",
                                        _position_id,
                                        *open_position_statuses_close,
                                    ),
                                )
                                exits_executed += 1
                                cur.execute(f"RELEASE SAVEPOINT {_sp}")
                                continue
                            else:
                                raise

                        if cur_price is None:
                            # Try to fall back to last known archive price instead of silently skipping
                            logger.warning(
                                f"[EXIT ENGINE] {symbol}: No current price available. Attempting fallback to archive price..."
                            )
                            fallback_price = self._get_last_valid_archive_price(cur, symbol, current_date)
                            if fallback_price is not None:
                                logger.info(
                                    f"[EXIT ENGINE] {symbol}: Using archive price ${fallback_price:.2f} "
                                    f"(current price unavailable, will mark as estimated)"
                                )
                                cur_price = fallback_price
                                # Mark that this exit will use an estimated price (for P&L reconciliation)
                                # so downstream knows not to trust the P&L until a real fill is confirmed
                                is_estimated_price_exit = True
                            else:
                                # No archive price available - truly unavailable, must skip
                                logger.critical(
                                    f"[EXIT ENGINE CRITICAL] {symbol}: No price data available (current or archive). "
                                    f"Cannot evaluate exit. Position remains open - retry when price data available."
                                )
                                _missing_price_err = RuntimeError(f"No price data available (current or archive) for {symbol}")
                                trade_errors += 1
                                _persist_exit_check_error(
                                    current_date,
                                    trade_id,
                                    _position_id,
                                    symbol,
                                    "MissingPriceData",
                                    str(_missing_price_err),
                                )
                                cur.execute(f"RELEASE SAVEPOINT {_sp}")
                                continue

                        days_held = (current_date - trade_date).days

                        # CRITICAL FIX: Clamp negative days_held to 0 (same-day entries should have 0 days, not negative)
                        # Negative values indicate data corruption (e.g., entry_date set to future date by mistake)
                        # Clamping prevents false "minimum hold not met" blocks on valid exits
                        if days_held < 0:
                            logger.warning(
                                f"{symbol}: days_held is negative ({days_held}) - data corruption detected. "
                                f"Clamping to 0 for exit evaluation. "
                                f"trade_date={trade_date}, current_date={current_date}"
                            )
                            days_held = 0

                        # CRITICAL: Check hard stop-loss BEFORE min_hold_days gate
                        # Hard stop-loss is unconditional capital preservation, not discretionary
                        # Same-day entries can (and must) exit on stop-loss
                        # CRITICAL FIX Session 20: Use init_stop (t.stop_loss_price from trade) not active_stop
                        # active_stop was using current_stop_price (running stop) instead of initial hard stop loss
                        cur_price_dec = Decimal(str(cur_price)) if not isinstance(cur_price, Decimal) else cur_price
                        hard_stop_dec = Decimal(str(init_stop)) if not isinstance(init_stop, Decimal) else init_stop
                        exit_signal: dict[str, Any] | None = None
                        if cur_price_dec <= hard_stop_dec:
                            # CRITICAL FIX: When stop is hit, use the stop price itself as the exit price
                            # instead of using the potentially stale cur_price from _fetch_recent_prices().
                            # Paper mode was using stale prices (fallback closes) as exit fills, creating
                            # 4-5% slippage. In reality, stops execute AT the stop price (or very close).
                            # Using hard_stop_dec ensures paper mode simulation matches real trading behavior.
                            exit_price_for_stop = hard_stop_dec
                            exit_signal = {
                                "stage": "stop",
                                "fraction": 1.0,
                                "reason": (
                                    f"STOP hit: ${float(cur_price_dec):.2f} <= ${float(hard_stop_dec):.2f} "
                                    "(hard capital preservation - bypasses min_hold_days)"
                                ),
                                "exit_price_override": float(exit_price_for_stop),  # Use stop price as fill
                            }
                        else:
                            # Get min_hold_days from config
                            # Hard stop-loss above already checked and not triggered
                            min_hold_val = self.config.get("min_hold_days")
                            if min_hold_val is None:
                                raise ValueError("CRITICAL: min_hold_days config missing. Cannot enforce minimum holding period.")
                            min_hold_days_check = int(min_hold_val)

                            if days_held < min_hold_days_check:
                                if self.verbose:
                                    logger.info(f"  {symbol}: hold (minimum hold period not met: {days_held}d held < {min_hold_days_check}d required)")
                                cur.execute(f"RELEASE SAVEPOINT {_sp}")
                                continue

                            exit_signal = self._evaluate_position(
                            cur,
                            symbol,
                            current_date,
                            Decimal(str(cur_price)),
                            Decimal(str(prev_close)) if prev_close is not None else None,
                            entry_price,
                            active_stop,
                            init_stop,
                            t1_price,
                            t2_price,
                            t3_price,
                            target_hits,
                            days_held,
                            dist_days_today,
                            t1_hit_time,
                            t2_hit_time,
                            t3_hit_time,
                            last_partial_exit_date,
                            partial_exits_log,
                        )

                        if not exit_signal:
                            t1_str = f"${float(t1_price):.2f}" if t1_price is not None else "--"

                            logger.info(
                                f"  {symbol}: hold (cur ${float(cur_price):.2f}, "
                                f"stop ${float(active_stop):.2f}, t1 {t1_str}, "
                                f"day {days_held}, hits {target_hits})"
                            )
                            cur.execute(f"RELEASE SAVEPOINT {_sp}")
                            continue

                        fraction = cast(float, exit_signal["fraction"])

                        stage = cast(str, exit_signal["stage"])

                        new_stop = cast(float | None, exit_signal.get("new_stop"))

                        # Route exit through executor (atomicity + audit logging)

                        # Stop-raise-only (fraction=0) skips exit_trade, just updates stop

                        logger.info(f"  {symbol}: {stage.upper()} - {cast(str, exit_signal['reason'])}")

                        if fraction > 0:
                            logger.info(f"      (exit {int(fraction * 100)}%)")

                        # For stop-raise-only, new_stop is required
                        if fraction == 0 and new_stop is None:
                            raise RuntimeError(
                                f"[EXIT_ENGINE] {symbol}: Stop-raise-only (fraction=0) requires new_stop price. "
                                f"Exit signal missing new_stop field. Cannot update stop without price."
                            )

                        # Route through executor for all cases (stop-raise-only when fraction=0)

                        # Pass cursor for transactional integrity: all exit updates in same transaction

                        # as position queries and state checks above (prevents orphaned state)

                        # CRITICAL FIX: Use exit_price_override if provided (for stop losses, use stop price)
                        exit_price_to_use = exit_signal.get("exit_price_override") if exit_signal else None
                        if exit_price_to_use is None:
                            exit_price_to_use = cur_price if fraction > 0 else None

                        result = self.executor.exit_trade(
                            trade_id=trade_id,
                            exit_price=exit_price_to_use,
                            exit_reason=cast(str, exit_signal["reason"]),
                            exit_fraction=fraction,  # 0 for stop-raise-only
                            exit_stage=stage,
                            new_stop_price=new_stop,
                            cur=cur,
                        )

                        if "success" not in result:
                            raise RuntimeError("Exit trade result missing 'success' field")
                        success = result["success"]
                        message = result["message"]

                        if fraction == 0 and success:
                            logger.info(f"      -> Stop raised to ${new_stop:.2f}")
                            stop_raises_executed += 1
                        elif success:
                            exits_executed += 1
                            logger.info(f"      -> {message}")
                        else:
                            logger.error(f"      -> FAILED: {message}")

                        cur.execute(f"RELEASE SAVEPOINT {_sp}")

                    except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, KeyError, RuntimeError) as _trade_err:
                        # CRITICAL FIX: Rollback to savepoint may itself fail if transaction is aborted.
                        # Wrap it in try-except to ensure we log the error and continue to the next position,
                        # rather than propagating a "current transaction is aborted" error that would abort
                        # exit coverage for all remaining positions in this batch.
                        transaction_aborted = False
                        rollback_err: Exception | None = None
                        try:
                            cur.execute(f"ROLLBACK TO SAVEPOINT {_sp}")
                        except psycopg2.Error as _rollback_err:
                            rollback_err = _rollback_err
                            # Check if the transaction is aborted - if so, we MUST halt this run
                            if "current transaction is aborted" in str(_rollback_err).lower():
                                transaction_aborted = True
                                logger.critical(
                                    f"[EXIT_ENGINE CRITICAL] Transaction aborted for {symbol}: {type(_rollback_err).__name__}: {_rollback_err}. "
                                    f"Cannot continue evaluating remaining positions - transaction state is unrecoverable."
                                )
                            else:
                                logger.error(
                                    f"[EXIT_ENGINE] Savepoint rollback failed for {symbol}: {type(_rollback_err).__name__}: {_rollback_err}. "
                                    f"This indicates a transaction error that should be investigated."
                                )

                        logger.error(
                            f"Exit check failed for {symbol} (trade {trade_id}): "
                            f"{type(_trade_err).__name__}: {_trade_err}"
                        )

                        # If transaction is aborted, we MUST halt immediately - subsequent positions would all fail
                        if transaction_aborted:
                            raise DatabaseError(
                                f"[EXIT_ENGINE CRITICAL] Transaction aborted - cannot continue evaluating positions. "
                                f"First abort occurred at symbol {symbol}. Halting exit engine."
                            ) from (rollback_err if rollback_err else None)

                        # Persist to an audit table, not just the logger - this process's stdout
                        # is gone the moment a scheduled/background run exits, and this is the
                        # only place a failed exit-check for an open position gets recorded.
                        # Written on an isolated connection (see _persist_exit_check_error) so an
                        # audit-insert failure can never depend on - or further damage - whatever
                        # state this position's own transaction/savepoint is already in.
                        # CRITICAL: Count error unconditionally - it occurred (we caught the exception)
                        # regardless of whether audit persistence succeeds. Audit is forensics,
                        # not the source of truth for whether an error happened. If audit fails,
                        # log it but still count the error.
                        trade_errors += 1
                        _persist_exit_check_error(
                            current_date,
                            trade_id,
                            _position_id,
                            symbol,
                            type(_trade_err).__name__,
                            str(_trade_err),
                        )
                        continue

                logger.info(f"\n{'=' * 70}")

                logger.info(
                    f"Exits executed: {exits_executed}/{len(trades)} positions "
                    f"({stop_raises_executed} stop-raises, {trade_errors} errors, {forced_closes_no_price} forced_closes_no_price)"
                )

                logger.info(f"{'=' * 70}\n")

                return exits_executed, stop_raises_executed, trade_errors, forced_closes_no_price

            except (ValueError, RuntimeError) as e:
                logger.error(f"Exit engine error (configuration or data): {type(e).__name__}: {e}")

                raise

            except DatabaseError as e:
                logger.critical(f"Exit engine database error (halting): {e}")

                raise

            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.exception(f"Unexpected error in exit engine: {type(e).__name__}: {e}")

                raise

    # ---------- Decision logic ----------

    def _evaluate_position(
        self,
        cur: PsycopgCursor[Any],
        symbol: str,
        current_date: _date,
        cur_price: Decimal | float | None,
        prev_close: Decimal | float | None,
        entry_price: Decimal | float,
        active_stop: Decimal | float,
        init_stop: Decimal | float,
        t1_price: Decimal | float | None,
        t2_price: Decimal | float | None,
        t3_price: Decimal | float | None,
        target_hits: int,
        days_held: int,
        dist_days_today: int | None,
        t1_hit_time: datetime | None = None,
        t2_hit_time: datetime | None = None,
        t3_hit_time: datetime | None = None,
        last_partial_exit_date: _date | None = None,
        partial_exits_log: str | None = None,
    ) -> dict[str, Any] | None:
        """Decide what exit to take, or None if no action is needed.

        Uses ExitStrategyChain to evaluate strategies in priority order.
        Each strategy returns an ExitSignal; first triggered signal wins.
        If none triggered, returns None - the caller's `if not exit_signal:` branch
        already exists specifically to handle this (log "hold", release savepoint,
        move to the next position).
        """
        if cur_price is None:
            raise RuntimeError(
                f"Exit evaluation failed for {symbol}: current price is None. "
                "Cannot evaluate exit conditions without current price. Check Alpaca price feed."
            )

        # CRITICAL: the hard stop-loss must never be gated by min_hold_days. This file's own
        # documented exit hierarchy lists it first specifically because it's an unconditional
        # "hard capital preservation rule", not a discretionary trend-following signal like the
        # other 11 checks below (which legitimately benefit from a min-hold buffer to avoid
        # same-day whipsaw exits). The min_hold_days gate below used to run BEFORE the
        # ExitStrategyChain existed at all - meaning a position that gapped/crashed through its
        # stop before min_hold_days was satisfied (min_hold_days=1 in production - the entire
        # entry day) would report "hold" and never exit. In execution_mode="auto" (real Alpaca
        # orders) the broker's own bracket stop-loss order is a backstop, but in paper/dry/
        # LOCAL_MODE (no real Alpaca order at all - see executor.py's _submit_and_validate_order)
        # this Python-side check is the ONLY stop-loss enforcement that exists, and even in auto
        # mode it's a real defense-in-depth gap if the broker order is ever cancelled/modified/
        # missed. Check the hard stop first, unconditionally, before the min-hold gate.
        cur_price_dec = Decimal(str(cur_price)) if not isinstance(cur_price, Decimal) else cur_price
        active_stop_dec = Decimal(str(active_stop)) if not isinstance(active_stop, Decimal) else active_stop
        if cur_price_dec <= active_stop_dec:
            return {
                "stage": "stop",
                "fraction": 1.0,
                "reason": (
                    f"STOP hit: ${float(cur_price_dec):.2f} <= ${float(active_stop_dec):.2f} "
                    "(hard capital preservation - not subject to min_hold_days)"
                ),
            }

        # CRITICAL FIX SESSION 41: Remove blanket min_hold_days gate that blocks ALL exits on same-day entries.
        # This was causing portfolio deadlock: 15 positions entered same-day cannot exit, blocking Phase 8 entries.
        # Solution: Allow target-level, distribution, and technical exits on same-day entries.
        # Only time-based exits are now gated to min_hold_days (via check_time_exit).
        # This allows immediate 50% exposure reduction on targets/distribution while blocking discretionary time exits.
        #
        # Historical context: This blanket gate was well-intentioned (Curtis Faith's 1-day hold minimum)
        # but it's TOO RIGID for a portfolio that hits capacity. If all 15 positions enter same-day:
        # - Old behavior: cannot exit ANY on same day -> portfolio stuck at 15/15
        # - New behavior: can reduce 50% via targets/distribution -> portfolio can make room for new entries
        # - Capital preservation (hard stops) already bypassed this gate (lines 950-965 above)
        # - Time-based discretionary exits still gated (see check_time_exit below)

        ctx = PositionContext(
            symbol=symbol,
            current_date=current_date,
            cur_price=Decimal(str(cur_price)) if not isinstance(cur_price, Decimal) else cur_price,
            prev_close=Decimal(str(prev_close)) if prev_close is not None else None,
            entry_price=Decimal(str(entry_price)) if not isinstance(entry_price, Decimal) else entry_price,
            active_stop=Decimal(str(active_stop)) if not isinstance(active_stop, Decimal) else active_stop,
            init_stop=Decimal(str(init_stop)) if not isinstance(init_stop, Decimal) else init_stop,
            t1_price=Decimal(str(t1_price)) if t1_price is not None and not isinstance(t1_price, Decimal) else t1_price,
            t2_price=Decimal(str(t2_price)) if t2_price is not None and not isinstance(t2_price, Decimal) else t2_price,
            t3_price=Decimal(str(t3_price)) if t3_price is not None and not isinstance(t3_price, Decimal) else t3_price,
            target_hits=target_hits,
            days_held=days_held,
            dist_days_today=dist_days_today,
            config=self.config,
            cur=cur,
            t1_hit_time=t1_hit_time,
            t2_hit_time=t2_hit_time,
            t3_hit_time=t3_hit_time,
            last_partial_exit_date=last_partial_exit_date,
            partial_exits_log=partial_exits_log,
        )

        # Evaluate all strategies in priority order using strategy chain
        from algo.trading.exit_strategies import ExitStrategyChain

        chain = ExitStrategyChain(self.config)
        signal = chain.evaluate(ctx, cur)

        if signal.triggered:
            return signal.to_dict()

        # No exit conditions met - hold the position. Must be None (falsy), not a "hold"
        # dict - see the min_hold_days branch above for why a truthy fraction=0.0 dict
        # here crashes the caller. This is the single most common outcome (a healthy
        # position with nothing currently triggered), so this bug fired on essentially
        # every ordinary exit evaluation - live-reproduced 2026-07-27: 7/7 open positions
        # crashed here in one run, all with "no exit conditions met."
        return None

    # ---------- Data helpers ----------

    def _fetch_alpaca_quote(self, symbol: str) -> float | dict[str, str | bool]:
        """Fetch real-time quote from Alpaca Data API.

        Returns:
            float: Valid price from Alpaca
            dict: {"data_unavailable": True, "reason": "..."} if paper mode sandbox 404

        Raises on API failure or missing credentials. Raises on critical API errors in live mode.

        When API returns status 200 but no valid price data:
        - Market open: Raises RuntimeError (API is broken, got 200 but no quote)
        - Market closed: Raises RuntimeError (caller must check market hours)

        Paper mode 404: Returns explicit data_unavailable marker instead of None (sandbox limitation)
        """

        try:
            creds = get_alpaca_credentials()

            key = creds.get("key")

            secret = creds.get("secret")

            if not key or not secret:
                raise RuntimeError(f"CRITICAL: Alpaca credentials missing. Cannot fetch quote for {symbol}.")

            data_url = get_alpaca_data_url()

            # Use latest quotes endpoint for real-time midpoint price

            # RETRY (found 2026-07-28, same bug class as order_manager.py/position_monitor.py's
            # send/cancel/qty fixes): a transient 429/503 used to fall into the generic `else`
            # branch below and raise immediately - the highest-stakes instance of this bug class
            # yet, since this quote feeds real-time stop-loss/exit evaluation. A retryable API
            # blip could silently cost a real exit check for this symbol this cycle (caught and
            # audited via algo_exit_check_errors, per migration 1169, but never actually retried).
            max_attempts = 3
            response = None
            for attempt in range(max_attempts):
                try:
                    # CRITICAL FIX 2026-08-03: /v2/quotes/latest is not a valid Alpaca endpoint -
                    # confirmed live it returns a genuine (not proxy/auth) 404 "endpoint not
                    # found" from Alpaca itself; the real path is /v2/stocks/quotes/latest. Also
                    # switched feed sip -> iex: this account has no SIP subscription (confirmed
                    # live: sip returns 403 "subscription does not permit querying recent SIP
                    # data" even on the corrected path) - iex is the free-tier feed and returns
                    # real quotes. Together these meant EVERY exit-engine quote lookup, for every
                    # symbol, on every run, always fell through to the paper-sandbox-404 branch
                    # and used database fallback pricing instead of a live quote.
                    response = requests.get(
                        f"{data_url}/v2/stocks/quotes/latest",
                        params={"symbols": symbol, "feed": "iex"},
                        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                        timeout=get_alpaca_timeout(),
                    )
                except (requests.Timeout, requests.ConnectionError) as e:
                    if attempt < max_attempts - 1:
                        wait_time = 2**attempt
                        logger.warning(
                            f"[EXIT_ENGINE] {symbol}: Alpaca quote API {type(e).__name__} - "
                            f"transient, retrying in {wait_time}s (attempt {attempt + 1}/{max_attempts})"
                        )
                        time.sleep(wait_time)
                        continue
                    raise
                if response.status_code in (429, 503) and attempt < max_attempts - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"[EXIT_ENGINE] {symbol}: Alpaca quote API {response.status_code} - "
                        f"transient, retrying in {wait_time}s (attempt {attempt + 1}/{max_attempts})"
                    )
                    time.sleep(wait_time)
                    continue
                break

            assert response is not None, "Response should be set after loop"
            if response.status_code == 200:
                data = response.json()

                # Validate API response structure
                if "quotes" not in data or not isinstance(data["quotes"], dict):
                    raise RuntimeError(
                        f"Alpaca quote API returned 200 but missing 'quotes' key or invalid type. Response: {data}"
                    )

                quotes = data["quotes"]

                if symbol not in quotes:
                    raise RuntimeError(
                        f"Alpaca quote API returned 200 but no data for {symbol}. "
                        f"Available symbols: {list(quotes.keys())}"
                    )

                quote = quotes[symbol]
                if not isinstance(quote, dict):
                    raise RuntimeError(f"Alpaca quote API returned invalid data type for {symbol}: {type(quote)}")

                # Calculate midpoint from bid/ask
                bid = quote.get("bp")

                ask = quote.get("ap")

                if bid is not None and ask is not None and bid > 0 and ask > 0:
                    midpoint = (float(bid) + float(ask)) / 2.0

                    return midpoint

                # Fallback to last price if available

                last_price = quote.get("lp")

                if last_price is not None:
                    return float(last_price)

                # Status 200 but no valid price data: check if market is open

                # During market open, this is an API error (we should get valid data)

                # During market closed, this is expected (no intraday quotes available)

                if MarketCalendar.is_market_open():
                    raise RuntimeError(
                        f"Alpaca quote API returned status 200 but no valid price data for {symbol}. "
                        f"Market is open; this indicates an API issue, not market closure."
                    )

                raise RuntimeError(
                    f"[EXIT_ENGINE] Cannot fetch intraday quote for {symbol}: market closed. "
                    f"Caller must check market hours before requesting intraday data."
                )

            elif response.status_code == 401:
                # Authentication failed - CRITICAL in auto mode, gracefully degrade in paper/dry modes
                execution_mode = self.config.get("execution_mode", "paper")
                if execution_mode == "auto":
                    # Live trading mode: 401 auth failure is a HARD STOP. Do NOT execute exits with stale
                    # database prices when broker communication fails. Broker is the source of truth for
                    # live positions. Using old prices to close positions without broker confirmation
                    # is incredibly dangerous (could close at completely wrong price, wrong time, etc.)
                    error_msg = (
                        f"[EXIT_ENGINE CRITICAL] {symbol}: Alpaca authentication failed (401) in LIVE trading mode. "
                        f"Cannot execute exits without valid broker communication. "
                        f"Cannot fall back to database prices when broker is unreachable. "
                        f"Check: Alpaca API credentials are valid, APCA_API_BASE_URL is correct, network connectivity. "
                        f"This position remains open - retry when broker communication restored."
                    )
                    logger.critical(error_msg)
                    raise RuntimeError(error_msg)
                else:
                    # Paper/dry modes: sandbox limitation, fall back to database prices for testing
                    logger.warning(
                        f"[EXIT_ENGINE] {symbol}: Alpaca quote API authentication failed (401) in {execution_mode} mode - "
                        f"falling back to database prices for exit evaluation"
                    )
                    return {"data_unavailable": True, "reason": f"Alpaca 401 auth failed - using database fallback"}

            elif response.status_code == 404:
                # 404 can mean two different things depending on execution mode:
                #
                # 1. Paper/Dry mode: Alpaca sandbox may not support all symbols, but we have
                #    valid price data in our database. Fall back to database prices rather than
                #    incorrectly marking valid positions as delisted.
                #
                # 2. Auto mode (live trading): A 404 in live Alpaca is a real error - the broker
                #    doesn't recognize this symbol at all. This could indicate delisted symbol,
                #    account permission change, or data corruption. Fail-fast.
                execution_mode = self.config.get("execution_mode", "paper")
                if execution_mode in ("paper", "dry", "review"):
                    # Sandbox limitation - return explicit data_unavailable marker for database fallback
                    logger.warning(
                        f"[EXIT_ENGINE] {symbol}: Alpaca quote API returned 404 - "
                        f"symbol unavailable in {execution_mode} sandbox. Database fallback pricing will be used."
                    )
                    return {"data_unavailable": True, "reason": f"Alpaca 404 in {execution_mode} sandbox"}
                else:
                    # Live trading mode (auto): 404 is a critical error
                    error_msg = (
                        f"[EXIT_ENGINE CRITICAL] {symbol}: Alpaca quote API returned 404 - "
                        f"symbol unavailable in live broker system (delisted or removed). "
                        f"Cannot execute exit for a symbol the broker doesn't have. "
                        f"This position is unexitable at the broker level. "
                        f"Manual intervention required: check if symbol is delisted or account permissions changed."
                    )
                    logger.critical(error_msg)
                    raise RuntimeError(error_msg)

            else:
                raise RuntimeError(f"Alpaca quote API error for {symbol}: status {response.status_code}")

        except requests.RequestException as e:
            raise ExchangeAPIError(f"Alpaca quote API error for {symbol}: {type(e).__name__}: {e}") from e

        except (RuntimeError, ValueError):
            raise

    def _fetch_recent_prices(
        self, cur: PsycopgCursor[Any], symbol: str, current_date: _date | datetime
    ) -> tuple[float | None, float | None]:
        """Return (current_price, previous_close) with intraday support.

        Strategy:
        1. Try to fetch real-time quote from Alpaca (for intraday stop checking)
        2. If market closed or symbol unavailable (404), fall back to daily closes
        3. If current date not available, use most recent historical prices
        4. If critical API error (not 404), propagate to caller for halt

        For 404 (delisted symbols in paper trading), use database fallback instead.
        """

        # CRITICAL FIX: `_fetch_alpaca_quote`'s own docstring documents that when the market is
        # closed it deliberately RAISES RuntimeError ("Caller must check market hours before
        # requesting intraday data") rather than returning a data_unavailable marker like the
        # paper-mode 401/404 branches do - the contract assumes THIS caller checks market hours
        # first. It never did: this function called `_fetch_alpaca_quote` unconditionally, so
        # outside market hours the RuntimeError propagated straight past the "fall back to daily
        # closes" logic below (step 2 of this docstring's own documented strategy), out through
        # `_evaluate_position`, and into the per-position exception handler as a counted
        # trade_error - meaning EVERY open position loses its stop/target/time-exit coverage for
        # the day if the exit engine ever runs after 4:00 PM ET (e.g. a delayed preclose run).
        # Confirmed live 2026-08-03: reproduced against 4 real open positions after market close.
        # Checking market hours here, before ever calling `_fetch_alpaca_quote`, honors the
        # documented contract and skips a doomed network round-trip.
        if MarketCalendar.is_market_open():
            # Try real-time quote first (intraday pricing, raises on genuine API failure)
            current_price = self._fetch_alpaca_quote(symbol)
        else:
            current_price = {"data_unavailable": True, "reason": "market_closed"}

        # Check if got valid price (not data_unavailable marker)
        if isinstance(current_price, (int, float)) and not isinstance(current_price, bool):
            # Got real-time quote; fetch previous close from daily data

            cur.execute(
                """

                SELECT close FROM price_daily

                WHERE symbol = %s AND date < %s

                ORDER BY date DESC LIMIT 1

                """,
                (symbol, current_date),
            )

            prev_row = cur.fetchone()

            prev_close = float(prev_row[0]) if prev_row and prev_row[0] is not None else None

            return current_price, prev_close

        # Fall back to daily closes (Alpaca unavailable, market closed, or data_unavailable marker)

        cur.execute(
            """

            SELECT date, close FROM price_daily

            WHERE symbol = %s AND date <= %s

            ORDER BY date DESC LIMIT 2

            """,
            (symbol, current_date),
        )

        rows = cur.fetchall()

        if not rows or len(rows[0]) < 2:
            # CRITICAL: No prices available up to current_date - fail-fast
            # Do NOT fall back to arbitrary historical prices from unknown dates.
            # Exit decisions require current market data. Using stale prices violates
            # fail-fast principle and masks data freshness issues.
            #
            # Falling back to "most recent available" means we might be using:
            # - Prices from days/weeks/months ago
            # - Delisted symbols with no recent data
            # - Data loading failures not yet detected
            #
            # All of these are critical conditions that should halt position monitoring,
            # not be masked with a warning log and a stale price fallback.
            error_msg = (
                f"[EXIT_PRICE CRITICAL] {symbol}: No price data available on/before {current_date}. "
                f"Cannot execute exits using stale or historical prices - current market data required. "
                f"This indicates: symbol delisted, data loader not yet run, or data gap. "
                f"Check price_daily table freshness and symbol validity. "
                f"Fail-fast: position cannot be monitored without current prices."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        cur_price = float(rows[0][1]) if rows[0][1] is not None else None

        if cur_price is None:
            error_msg = f"[EXIT_PRICE_NULL] Current price is NULL for {symbol}"

            logger.error(error_msg)

            raise RuntimeError(error_msg)

        if len(rows) < 2:
            error_msg = f"[EXIT_PRICE_SINGLE_DAY] Insufficient price history for {symbol} (need 2+ dates)"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        prev_close_raw = rows[1][1]
        if prev_close_raw is None:
            error_msg = f"Previous close is NULL for {symbol} on {rows[1][0]}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        try:
            prev_close = float(prev_close_raw)
        except (ValueError, TypeError) as e:
            error_msg = f"Cannot convert previous close to float for {symbol}: {prev_close_raw}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

        return cur_price, prev_close

    def _get_last_valid_archive_price(
        self, cur: PsycopgCursor[Any], symbol: str, current_date: _date | datetime
    ) -> float | None:
        """Get most recent available price for a delisted/unavailable symbol.

        Used when current price cannot be fetched (delisted symbol, API error).
        Returns last known close price from price_daily before or on current_date.
        Returns None if no historical price data exists.
        """
        cur.execute(
            """
            SELECT close FROM price_daily
            WHERE symbol = %s AND date <= %s
            ORDER BY date DESC LIMIT 1
            """,
            (symbol, current_date),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            try:
                return float(row[0])
            except (ValueError, TypeError):
                logger.warning(f"[EXIT_ENGINE] Cannot convert archive price to float for {symbol}: {row[0]}")
                return None
        return None

    def _fetch_market_dist_days(self, cur: PsycopgCursor[Any], current_date: _date | datetime) -> int | None:
        # market_health_daily.distribution_days_4w is only populated by the ~2-3am morning
        # loader, which runs before MarketExposure has enough same-day data to compute a
        # real distribution-day count - that row is written with distribution_days_4w=NULL
        # and never refreshed later in the day. market_exposure_daily.distribution_days is
        # the same underlying computation (MarketExposure.compute()), but gets a real value
        # once recomputed later in the trading day/EOD - read from there instead, and skip
        # any NULL rows rather than trusting "most recent date" to also mean "most recent
        # populated value" (confirmed live: today's market_health_daily row had NULL while
        # market_exposure_daily's same-day row already had a real count).
        cur.execute(
            """
            SELECT distribution_days, data_unavailable, reason
            FROM market_exposure_daily
            WHERE date <= %s AND distribution_days IS NOT NULL
            ORDER BY date DESC LIMIT 1
            """,
            (current_date,),
        )

        row = cur.fetchone()

        if not row:
            raise RuntimeError(
                f"[MARKET_DIST_DAYS_MISSING] Market distribution data unavailable for {current_date}. "
                f"Cannot evaluate exit conditions - distribution day counts are required for risk control decisions."
            )
        if row[1]:
            raise RuntimeError(
                f"[MARKET_DIST_DAYS_MISSING] Market exposure data marked unavailable for {current_date}: "
                f"{row[2] or 'no reason provided'}. Cannot evaluate exit conditions without valid distribution "
                f"day counts."
            )
        return int(row[0])

    def _is_pulling_back(self, cur: PsycopgCursor[Any], symbol: str, current_date: _date | datetime) -> bool:
        """Requires either 2-3% decline from recent high OR 2+ days below 5-day high.
        Real pullbacks show clear consolidation, not just a 0.5% afternoon dip.
        This prevents hair-trigger exits on winners.
        """
        cur.execute(
            """SELECT close, high FROM price_daily
               WHERE symbol = %s AND date <= %s
               ORDER BY date DESC LIMIT 6""",
            (symbol, current_date),
        )

        rows = cur.fetchall()

        if len(rows) < 3:
            # FAIL-FAST: Cannot evaluate pullback with insufficient price history
            # Returning False (no pullback) when we cannot verify pullback status masks
            # data quality issues - a position might be extended without confirmation
            # Pullback detection requires 3+ days of price data to be reliable
            raise ValueError(
                f"[EXIT_ENGINE PULLBACK] {symbol}: Insufficient price history ({len(rows)} days, need 3+). "
                f"Cannot evaluate pullback without complete price data. "
                f"Fail-fast to prevent blind exit decisions on data gaps."
            )

        cur_close = Decimal(str(rows[0][0]))

        valid_highs = [Decimal(str(r[1])) for r in rows[:5] if r[1] is not None]
        if not valid_highs:
            raise RuntimeError(
                "Pullback detection failed: no valid high prices in recent 5 days. "
                "Cannot assess pullback with missing market data. Verify price_daily has complete high prices."
            )

        recent_high = max(valid_highs)

        if recent_high <= 0:
            raise RuntimeError(
                f"Pullback detection failed: recent_high is {recent_high} (must be > 0). "
                "Cannot compute pullback percentage with invalid price data."
            )

        pullback_pct = float(
            ((recent_high - cur_close) / recent_high * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )

        if pullback_pct >= 2.0:
            return True

        # OR check if consolidated below high for 2+ days

        days_below_high = sum(1 for r in rows[:5] if Decimal(str(r[0])) < recent_high * Decimal("0.98"))

        return days_below_high >= 2

    def _rs_line_breaking(self, cur: PsycopgCursor[Any], symbol: str, current_date: _date | datetime) -> bool:
        """RS line (stock/SPY ratio) breaking below its 50-day MA = exit signal."""

        cur.execute(
            """

            WITH ratio AS (

                SELECT s.date,

                       s.close::numeric / NULLIF(spy.close, 0) AS rs

                FROM price_daily s

                JOIN price_daily spy ON spy.symbol='SPY' AND spy.date=s.date

                WHERE s.symbol = %s AND s.date <= %s

                ORDER BY s.date DESC LIMIT 60

            ),

            ranked AS (

                SELECT rs, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn FROM ratio

            )

            SELECT

                (SELECT rs FROM ranked WHERE rn = 1) AS cur,

                (SELECT AVG(rs) FROM ranked WHERE rn BETWEEN 2 AND 51) AS rs_50dma

            """,
            (symbol, current_date),
        )

        row = cur.fetchone()

        if not row or len(row) < 2 or row[0] is None or row[1] is None:
            raise ValueError(f"Insufficient RS data for {symbol} to calculate RS line break")

        cur_rs = Decimal(str(row[0]))

        rs_50 = Decimal(str(row[1]))

        return cur_rs < rs_50 * Decimal("0.99")

    def _eight_week_rule_active(
        self,
        cur: PsycopgCursor[Any],
        symbol: str,
        current_date: _date,
        entry_price: float,
        days_held: int,
        threshold_pct: float,
        window_days: int,
    ) -> bool:
        """O'Neil 8-week rule: if stock gained 20%+ in first 3 weeks, hold for 8 weeks."""

        if days_held < window_days:
            return False

        cur.execute(
            """

            SELECT MAX(close) FROM price_daily

            WHERE symbol = %s

              AND date >= %s::date - MAKE_INTERVAL(days => %s)

              AND date <= %s::date - MAKE_INTERVAL(days => %s)

            """,
            (
                symbol,
                current_date,
                days_held,
                current_date,
                max(0, days_held - window_days),
            ),
        )

        row = cur.fetchone()

        if row is None or len(row) < 1 or row[0] is None:
            raise ValueError(f"No price data for {symbol} in 8-week window")

        max_close_in_window = Decimal(str(row[0]))

        if entry_price <= 0:
            raise ValueError(f"Invalid entry price for {symbol}: {entry_price}")

        gain_pct = float(
            ((max_close_in_window - Decimal(str(entry_price))) / Decimal(str(entry_price)) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )

        return gain_pct >= threshold_pct

    def _chandelier_or_ema_stop(
        self, cur: PsycopgCursor[Any], symbol: str, current_date: _date | datetime, days_held: int
    ) -> float | None:
        """Trailing stop: chandelier (3xATR from highest high) for first 10d,

        then 21-EMA after."""

        switch_val = self.config.get("switch_to_21ema_after_days")

        if switch_val is None:
            raise ValueError(
                "CRITICAL: switch_to_21ema_after_days config missing. Cannot determine EMA switch point for trailing stop."
            )

        switch_days = int(switch_val)

        if days_held >= switch_days:
            cur.execute(
                """

                WITH d AS (

                    SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn

                    FROM price_daily WHERE symbol = %s AND date <= %s

                    ORDER BY date DESC LIMIT 30

                )

                SELECT close FROM d ORDER BY rn DESC

                """,
                (symbol, current_date),
            )

            rows = cur.fetchall()

            if len(rows) < 21:
                raise ValueError(f"Insufficient price data for {symbol} to calculate 21-EMA stop")

            closes = [Decimal(str(r[0])) for r in rows]

            k = Decimal(2) / Decimal(22)

            ema = closes[0]

            for c in closes[1:]:
                ema = c * k + ema * (Decimal(1) - k)

            stop_price = ema * Decimal("0.99")

            return float(stop_price.quantize(Decimal("0.01"), rounding=ROUND_DOWN))

        else:
            cur.execute(
                """

                WITH d AS (

                    SELECT pd.high, td.atr,

                           ROW_NUMBER() OVER (ORDER BY pd.date DESC) AS rn

                    FROM price_daily pd

                    LEFT JOIN technical_data_daily td ON td.symbol = pd.symbol AND td.date = pd.date

                    WHERE pd.symbol = %s AND pd.date <= %s

                    ORDER BY pd.date DESC LIMIT %s

                )

                SELECT MAX(high) AS hh,

                       (SELECT atr FROM d WHERE rn = 1) AS cur_atr

                FROM d

                """,
                (symbol, current_date, max(days_held, 5)),
            )

            row = cur.fetchone()

            if not row or len(row) < 2 or row[0] is None or row[1] is None:
                raise ValueError(f"Insufficient data for {symbol} to calculate chandelier stop")

            hh = float(row[0])

            atr = float(row[1])

            mult_val = self.config.get("chandelier_atr_mult")

            if mult_val is None:
                raise ValueError(
                    "CRITICAL: chandelier_atr_mult config missing. Cannot calculate chandelier trailing stop."
                )

            mult = float(mult_val)

            stop_value = Decimal(str(hh)) - (Decimal(str(mult)) * Decimal(str(atr)))
            return float(stop_value.quantize(Decimal("0.01"), rounding=ROUND_DOWN))

    def _get_td_state(self, cur: PsycopgCursor[Any], symbol: str, current_date: _date | datetime) -> dict[str, Any]:
        """Return full TD state dict (for both 9 and 13 detection).



        Fail-fast  - if TD Sequential cannot be computed, raises exception.

        TD Sequential is a required exit signal for positions.

        """

        sc = SignalComputer(self.config)

        td_state = sc.td_sequential(symbol, current_date)

        if not td_state:
            raise ValueError(f"TD Sequential calculation failed for {symbol}")

        # Validate required TD Sequential fields are present
        required_fields = ["combo_13_complete", "setup_type", "countdown", "countdown_complete"]
        missing_fields = [f for f in required_fields if f not in td_state]
        if missing_fields:
            raise ValueError(
                f"TD Sequential incomplete for {symbol}: missing fields {missing_fields}. "
                f"Cannot determine exit triggers. Calculation returned: {td_state}"
            )

        return td_state

    def _is_minervini_break(
        self, cur: PsycopgCursor[Any], symbol: str, current_date: _date | datetime, cur_price: float
    ) -> bool:
        """Close < 50-DMA OR (close < EMA(21) AND volume > 50-day avg)."""

        interval_50d = get_interval_sql("50d")
        cur.execute(
            f"""

            SELECT td.sma_50, td.ema_21,

                   (SELECT volume FROM price_daily p WHERE p.symbol = td.symbol AND p.date = td.date) AS vol,

                   (SELECT AVG(volume) FROM price_daily p

                     WHERE p.symbol = td.symbol AND p.date <= td.date

                       AND p.date >= td.date - {interval_50d}) AS avg_vol_50

            FROM technical_data_daily td

            WHERE td.symbol = %s AND td.date <= %s

            ORDER BY td.date DESC LIMIT 1

            """,
            (symbol, current_date),
        )

        row = cur.fetchone()

        if row is None:
            raise ValueError(
                f"Cannot evaluate Minervini break for {symbol}: technical_data_daily missing for {current_date}"
            )

        sma_50, ema_21, vol, avg_vol_50 = row

        sma_50 = Decimal(str(sma_50)) if sma_50 is not None else None

        ema_21 = Decimal(str(ema_21)) if ema_21 is not None else None

        if vol is None:
            raise ValueError(f"Volume data missing for {symbol}; cannot evaluate volume-based exits")
        vol = float(vol)

        if avg_vol_50 is None:
            raise ValueError(f"50-day average volume missing for {symbol}; cannot evaluate relative volume")
        avg_vol_50 = float(avg_vol_50)

        cur_price_decimal = Decimal(str(cur_price))

        # Clean break of 50-DMA

        if sma_50 is not None and cur_price_decimal < sma_50 * Decimal("0.99"):
            return True

        # Break of EMA(21) on rising volume (institutional selling)

        ema_21_float = float(ema_21) if ema_21 is not None else None

        if ema_21_float is not None and cur_price < ema_21_float and avg_vol_50 > 0 and vol > avg_vol_50 * 1.15:
            return True

        return False

    def _check_volume_spike(
        self, cur: PsycopgCursor[Any], symbol: str, current_date: _date | datetime, volume_multiplier: float
    ) -> bool:

        interval_50d = get_interval_sql("50d")
        cur.execute(
            f"""

            SELECT pd.volume,

                   (SELECT AVG(volume) FROM price_daily p

                    WHERE p.symbol = pd.symbol

                      AND p.date <= pd.date

                      AND p.date > pd.date - {interval_50d}) AS avg_vol_50

            FROM price_daily pd

            WHERE pd.symbol = %s AND pd.date = %s

            """,
            (symbol, current_date),
        )

        row = cur.fetchone()

        if not row or len(row) < 2 or row[0] is None or row[1] is None:
            raise ValueError(f"Volume data unavailable for {symbol} on {current_date}")

        today_vol = float(row[0])

        avg_vol = float(row[1])

        return today_vol >= avg_vol * volume_multiplier

    def _compute_gain_last_n_days(
        self, cur: PsycopgCursor[Any], symbol: str, current_date: _date | datetime, n_days: int
    ) -> float | None:

        cur.execute(
            """

            WITH prices AS (

                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn

                FROM price_daily

                WHERE symbol = %s AND date <= %s

                ORDER BY date DESC LIMIT %s

            )

            SELECT

                (SELECT close FROM prices WHERE rn = 1) AS current_close,

                (SELECT close FROM prices WHERE rn = %s) AS close_n_days_ago

            """,
            (symbol, current_date, n_days + 1, n_days + 1),
        )

        row = cur.fetchone()

        if not row or len(row) < 2 or row[0] is None or row[1] is None:
            raise ValueError(f"Insufficient {n_days}-day price data for {symbol}")

        current = Decimal(str(row[0]))

        prior = Decimal(str(row[1]))

        if prior <= 0:
            raise ValueError(f"Invalid price data for {symbol}: prior close = {prior}")

        return float(((current - prior) / prior * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
