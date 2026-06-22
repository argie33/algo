#!/usr/bin/env python3
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, cast

import psycopg2
import requests

from algo.infrastructure import get_alpaca_timeout
from algo.infrastructure.market_calendar import MarketCalendar
from algo.signals import SignalComputer
from algo.trading import TradeExecutor
from algo.trading.exceptions import DatabaseError, ExchangeAPIError
from config.api_endpoints import get_alpaca_data_url
from config.credential_manager import get_alpaca_credentials
from utils.db import DatabaseContext
from utils.trading import PositionStatus, TradeStatus

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

try:
    from trade_performance_auditor import TradePerformanceAuditor

except ImportError:
    TradePerformanceAuditor = None

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
        current_date: datetime,
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
        config: Any = None,
        cur: Any = None,
        t1_hit_time: Any | None = None,
        t2_hit_time: Any | None = None,
        t3_hit_time: Any | None = None,
    ) -> None:
        self.symbol = symbol
        self.current_date = current_date
        self.cur_price = cur_price
        self.prev_close = prev_close
        self.entry_price = entry_price
        self.active_stop = active_stop
        self.init_stop = init_stop
        self.t1_price = t1_price
        self.t2_price = t2_price
        self.t3_price = t3_price
        self.target_hits = target_hits
        self.days_held = days_held
        self.dist_days_today = dist_days_today
        self.t1_hit_time = t1_hit_time
        self.t2_hit_time = t2_hit_time
        self.t3_hit_time = t3_hit_time
        self.config = config
        self.cur = cur

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
        """Minervini break: trend-following exit on moving average break."""
        if engine._is_minervini_break(self.cur, self.symbol, self.current_date, float(self.cur_price)):
            return (
                True,
                {
                    "stage": "stop",
                    "fraction": 1.0,
                    "reason": "Minervini trend break: closed below key MA on volume",
                },
            )
        return False, None

    def check_rs_line_break(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """RS line break: relative strength deterioration vs SPY."""
        if "exit_on_rs_line_break_50dma" not in self.config:
            raise ValueError(
                "CRITICAL: 'exit_on_rs_line_break_50dma' config missing. "
                "Cannot proceed with exit rules  - risk controls undefined."
            )
        if self.config["exit_on_rs_line_break_50dma"]:
            if engine._rs_line_breaking(self.cur, self.symbol, self.current_date):
                return (
                    True,
                    {
                        "stage": "stop",
                        "fraction": 1.0,
                        "reason": "RS line broke below 50-DMA  - relative strength deterioration",
                    },
                )
        return False, None

    def check_time_exit(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """Time-based exit with O'Neil 8-week rule override."""
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
                self.entry_price,
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

    def _was_target_hit_today(self, hit_time: Any | None) -> bool:
        """Check if target was already hit today."""
        if hit_time is None:
            return False
        hit_date = hit_time.date() if hasattr(hit_time, "date") else hit_time
        return cast(bool, hit_date == self.current_date.date())

    def check_target_t1(self, engine: ExitEngine) -> tuple[bool, dict[str, Any] | None]:
        """T1 target exit (1.5R): 50% position reduction."""
        if self.target_hits == 0 and self.t1_price is not None and self.cur_price >= self.t1_price:
            if self._was_target_hit_today(self.t1_hit_time):
                return False, None
            require_pb = bool(self.config.get("require_target_pullback", False))
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
        if self.target_hits == 1 and self.t2_price is not None and self.cur_price >= self.t2_price:
            if self._was_target_hit_today(self.t2_hit_time):
                return False, None
            require_pb = bool(self.config.get("require_target_pullback", False))
            if not require_pb or engine._is_pulling_back(self.cur, self.symbol, self.current_date):
                stop_for_t2 = max(self.active_stop, self.t1_price) if self.t1_price is not None else self.active_stop
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
        if self.target_hits == 2 and self.t3_price is not None and self.cur_price >= self.t3_price:
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
                if td_state.get("combo_13_complete") and td_state.get("setup_type") == "sell":
                    return (
                        True,
                        {
                            "stage": "td_combo_13",
                            "fraction": 1.0,
                            "reason": f"TD Combo 13-count exhaustion (FULL EXIT, R={float(r_mult):.2f})",
                        },
                    )
                if td_state.get("completed_9") and td_state.get("setup_type") == "sell":
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
            if self.dist_days_today > max_dd:
                return (
                    True,
                    {
                        "stage": "distribution",
                        "fraction": 0.5,
                        "new_stop": max(self.active_stop, self.entry_price),
                        "reason": f"Market distribution: {self.dist_days_today} dist days > {max_dd}  - reducing 50%, stop raised to breakeven",
                    },
                )
        return False, None


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
            "move_to_breakeven_r",
            "trailing_stop_atr_multiplier",
        ]
        missing = [k for k in required_keys if k not in config]
        if missing:
            raise ValueError(
                f"ExitEngine config missing required keys: {missing}. "
                f"Cannot initialize exit engine without these values."
            )

    def check_and_execute_exits(self, current_date=None) -> int:
        """Check all open positions for exit conditions and execute."""

        if not current_date:
            current_date = datetime.now(timezone.utc).date()

        auditor = TradePerformanceAuditor(self.config) if TradePerformanceAuditor else None

        with DatabaseContext("write") as cur:
            try:
                logger.info(f"\n{'=' * 70}")

                logger.info(f"EXIT ENGINE CHECK - {current_date}")

                logger.info(f"{'=' * 70}\n")

                cur.execute(
                    """

                    SELECT t.trade_id, t.symbol, t.entry_price, t.stop_loss_price,

                           t.target_1_price, t.target_2_price, t.target_3_price,

                           t.trade_date,

                           p.position_id, p.quantity, p.target_levels_hit,

                           p.current_stop_price, p.target_1_hit_time, p.target_2_hit_time, p.target_3_hit_time

                    FROM algo_trades t

                    JOIN algo_positions p ON t.trade_id = ANY(p.trade_ids_arr)

                    WHERE t.status IN (%s, %s) AND p.status = %s AND p.quantity > 0

                    ORDER BY t.trade_date ASC

                    """,
                    (
                        TradeStatus.OPEN.value,
                        TradeStatus.PENDING.value,
                        PositionStatus.OPEN.value,
                    ),
                )

                trades = cur.fetchall()

                if not trades:
                    logger.info("No open positions.\n")

                    return 0

                # Cache market distribution-day status once for the run

                dist_days_today = self._fetch_market_dist_days(cur, current_date)

                exits_executed = 0

                for row in trades:
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
                    ) = row

                    # Issue #22: Lock position row to prevent concurrent exits (TOCTOU race)

                    cur.execute(
                        "SELECT status FROM algo_positions WHERE position_id = %s FOR UPDATE",
                        (_position_id,),
                    )

                    status_row = cur.fetchone()

                    status = status_row[0] if status_row else None

                    if status != "open":
                        logger.debug(f"Position {symbol} already closed, skipping exit check")

                        continue

                    try:
                        entry_price = Decimal(str(entry_price))

                        init_stop = Decimal(str(init_stop))

                        active_stop = Decimal(str(current_stop)) if current_stop else init_stop

                        t1_price = Decimal(str(t1_price)) if t1_price else None

                        t2_price = Decimal(str(t2_price)) if t2_price else None

                        t3_price = Decimal(str(t3_price)) if t3_price else None

                        if target_hits is None:
                            raise ValueError(f"{symbol}: target_hits is NULL in database  - data corruption detected")

                        target_hits = int(target_hits)

                    except (TypeError, ValueError) as e:
                        raise ValueError(f"Cannot evaluate exit checks for {symbol}: invalid price data  - {e}") from e

                    cur_price, prev_close = self._fetch_recent_prices(cur, symbol, current_date)

                    if cur_price is None:
                        raise RuntimeError(
                            f"[EXIT ENGINE] Critical: current price unavailable for {symbol} "
                            " - cannot evaluate exits without market data"
                        )

                    days_held = (current_date - trade_date).days

                    # Enforce minimum holding period (no same-day exits per Curtis Faith)

                    if days_held < 1:
                        if self.verbose:
                            logger.info(f"  {symbol}: hold (too new, need 1d hold minimum, held {days_held}d)")

                        continue

                    exit_signal = self._evaluate_position(
                        cur,
                        symbol,
                        current_date,
                        cur_price,
                        prev_close,
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
                    )

                    if not exit_signal:
                        t1_str = f"${float(t1_price):.2f}" if t1_price is not None else "--"

                        logger.info(
                            f"  {symbol}: hold (cur ${float(cur_price):.2f}, "
                            f"stop ${float(active_stop):.2f}, t1 {t1_str}, "
                            f"day {days_held}, hits {target_hits})"
                        )

                        continue

                    fraction = exit_signal["fraction"]

                    stage = exit_signal["stage"]

                    new_stop = exit_signal.get("new_stop")

                    # Route exit through executor (atomicity + audit logging)

                    # Stop-raise-only (fraction=0) skips exit_trade, just updates stop

                    logger.info(f"  {symbol}: {stage.upper()} - {exit_signal['reason']}")

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

                    result = self.executor.exit_trade(
                        trade_id=trade_id,
                        exit_price=cur_price if fraction > 0 else None,
                        exit_reason=exit_signal["reason"],
                        exit_fraction=fraction,  # 0 for stop-raise-only
                        exit_stage=stage,
                        new_stop_price=new_stop,
                        cur=cur,
                    )

                    if fraction == 0 and result.get("success"):
                        logger.info(f"      -> Stop raised to ${new_stop:.2f}")

                        exits_executed += 1

                    elif result.get("success"):
                        exits_executed += 1

                        logger.info(f"      -> {result['message']}")

                    else:
                        logger.error(f"      -> FAILED: {result.get('message')}")

                logger.info(f"\n{'=' * 70}")

                logger.info(f"Exits executed: {exits_executed}/{len(trades)} positions")

                logger.info(f"{'=' * 70}\n")

                # NEW: Audit closed trades for performance (Phase 2 integration)

                try:
                    cur.execute(
                        """

                        SELECT DISTINCT trade_id FROM algo_trades

                        WHERE status = %s AND exit_date = %s

                    """,
                        (TradeStatus.CLOSED.value, current_date),
                    )

                    closed_trades = cur.fetchall()

                    for (trade_id,) in closed_trades:
                        if auditor:
                            auditor.audit_exit(trade_id)

                except (DatabaseError, ValueError) as audit_err:
                    logger.error(
                        f"Warning: Failed to audit closed trades (non-blocking): {type(audit_err).__name__}: {audit_err}"
                    )

                return exits_executed

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
        cur,
        symbol,
        current_date,
        cur_price,
        prev_close,
        entry_price,
        active_stop,
        init_stop,
        t1_price,
        t2_price,
        t3_price,
        target_hits,
        days_held,
        dist_days_today,
        t1_hit_time=None,
        t2_hit_time=None,
        t3_hit_time=None,
    ) -> dict[str, Any]:
        """Decide what exit to take (or hold decision).

        Uses ExitStrategyChain to evaluate strategies in priority order.
        Each strategy returns an ExitSignal; first triggered signal wins.
        If none triggered, returns hold decision.
        """
        min_hold_val = self.config.get("min_hold_days")
        if min_hold_val is None:
            raise ValueError("CRITICAL: min_hold_days config missing. Cannot enforce minimum holding period.")

        min_hold_days = int(min_hold_val)
        if days_held < min_hold_days:
            return {
                "stage": "hold",
                "fraction": 0.0,
                "reason": f"Minimum holding period not met: {days_held} days held < {min_hold_days} required",
            }

        # Consolidate all context into PositionContext for strategy evaluation
        ctx = PositionContext(
            symbol=symbol,
            current_date=current_date,
            cur_price=Decimal(str(cur_price)),
            prev_close=Decimal(str(prev_close)) if prev_close is not None else None,
            entry_price=Decimal(str(entry_price)),
            active_stop=Decimal(str(active_stop)),
            init_stop=Decimal(str(init_stop)),
            t1_price=Decimal(str(t1_price)) if t1_price is not None else None,
            t2_price=Decimal(str(t2_price)) if t2_price is not None else None,
            t3_price=Decimal(str(t3_price)) if t3_price is not None else None,
            target_hits=target_hits,
            days_held=days_held,
            dist_days_today=dist_days_today,
            config=self.config,
            cur=cur,
            t1_hit_time=t1_hit_time,
            t2_hit_time=t2_hit_time,
            t3_hit_time=t3_hit_time,
        )

        # Evaluate all strategies in priority order using strategy chain
        from algo.trading.exit_strategies import ExitStrategyChain

        chain = ExitStrategyChain(self.config)
        signal = chain.evaluate(ctx, cur)

        if signal.triggered:
            return signal.to_dict()

        # No exit conditions met - hold the position
        return {
            "stage": "hold",
            "fraction": 0.0,
            "reason": "No exit conditions met",
        }

    # ---------- Data helpers ----------

    def _fetch_alpaca_quote(self, symbol: str) -> float | None:
        """Fetch real-time quote from Alpaca Data API.



        Raises on API failure or missing credentials. Returns None only if market is closed.



        When API returns status 200 but no valid price data:

        - Market open: Raises RuntimeError (API is broken, got 200 but no quote)

        - Market closed: Returns None (expected; market closed means no intraday quotes)

        """

        try:
            creds = get_alpaca_credentials()

            key = creds.get("key")

            secret = creds.get("secret")

            if not key or not secret:
                raise RuntimeError(f"CRITICAL: Alpaca credentials missing. Cannot fetch quote for {symbol}.")

            data_url = get_alpaca_data_url()

            # Use latest quotes endpoint for real-time midpoint price

            response = requests.get(
                f"{data_url}/v2/quotes/latest",
                params={"symbols": symbol, "feed": "sip"},
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
                timeout=get_alpaca_timeout(),
            )

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

                return None

            elif response.status_code == 401:
                raise RuntimeError(f"Alpaca quote API authentication failed for {symbol}")

            else:
                raise RuntimeError(f"Alpaca quote API error for {symbol}: status {response.status_code}")

        except requests.RequestException as e:
            raise ExchangeAPIError(f"Alpaca quote API error for {symbol}: {type(e).__name__}: {e}") from e

        except (RuntimeError, ValueError):
            raise

    def _fetch_recent_prices(self, cur, symbol: str, current_date) -> tuple[float | None, float | None]:
        """Return (current_price, previous_close) with intraday support.



        Strategy:

        1. Try to fetch real-time quote from Alpaca (for intraday stop checking)

        2. If market closed (quote returns None), fall back to daily closes

        3. If API fails (raises exception), propagate to caller for immediate halt



        This ensures stop losses execute on current prices during market hours.

        On API failure, exit engine halts rather than using stale daily closes.

        """

        # Try real-time quote first (intraday pricing, raises on API failure)

        current_price = self._fetch_alpaca_quote(symbol)

        if current_price is not None:
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

        # Fall back to daily closes (market closed or API unavailable)

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
            error_msg = f"Price data missing for {symbol} - cannot evaluate exits"

            logger.error(error_msg)

            raise RuntimeError(error_msg)

        cur_price = float(rows[0][1]) if rows[0][1] is not None else None

        if cur_price is None:
            error_msg = f"Current price is NULL for {symbol}"

            logger.error(error_msg)

            raise RuntimeError(error_msg)

        prev_close = float(rows[1][1]) if len(rows) > 1 and rows[1][1] is not None else None

        return cur_price, prev_close

    def _fetch_market_dist_days(self, cur, current_date) -> int | None:

        cur.execute(
            """

            SELECT distribution_days_4w FROM market_health_daily

            WHERE date <= %s ORDER BY date DESC LIMIT 1

            """,
            (current_date,),
        )

        row = cur.fetchone()

        return int(row[0]) if row and row[0] is not None else None

    def _is_pulling_back(self, cur, symbol: str, current_date) -> bool:
        """Requires either 2-3% decline from recent high OR 2+ days below 5-day high.



        Real pullbacks show clear consolidation, not just a 0.5% afternoon dip.

        This prevents hair-trigger exits on winners."""

        cur.execute(
            """

            SELECT close, high FROM price_daily

            WHERE symbol = %s AND date <= %s

            ORDER BY date DESC LIMIT 6

            """,
            (symbol, current_date),
        )

        rows = cur.fetchall()

        if len(rows) < 3:
            return False

        cur_close = Decimal(str(rows[0][0]))

        recent_high = max(Decimal(str(r[1])) if r[1] is not None else Decimal(str(r[0])) for r in rows[:5])

        pullback_pct = (
            float(
                ((recent_high - cur_close) / recent_high * Decimal(100)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )
            if recent_high > 0
            else 0
        )

        if pullback_pct >= 2.0:
            return True

        # OR check if consolidated below high for 2+ days

        days_below_high = sum(1 for r in rows[:5] if Decimal(str(r[0])) < recent_high * Decimal("0.98"))

        return days_below_high >= 2

    def _rs_line_breaking(self, cur, symbol: str, current_date) -> bool:
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

        if not row or row[0] is None or row[1] is None:
            raise ValueError(f"Insufficient RS data for {symbol} to calculate RS line break")

        cur_rs = Decimal(str(row[0]))

        rs_50 = Decimal(str(row[1]))

        return cur_rs < rs_50 * Decimal("0.99")

    def _eight_week_rule_active(
        self,
        cur,
        symbol,
        current_date,
        entry_price,
        days_held,
        threshold_pct,
        window_days,
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

        if not row or not row[0]:
            raise ValueError(f"No price data for {symbol} in 8-week window")

        max_close_in_window = Decimal(str(row[0]))

        if entry_price <= 0:
            raise ValueError(f"Invalid entry price for {symbol}: {entry_price}")

        gain_pct = float(
            ((max_close_in_window - Decimal(str(entry_price))) / Decimal(str(entry_price)) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )

        return cast(bool, gain_pct >= threshold_pct)

    def _chandelier_or_ema_stop(self, cur, symbol: str, current_date, days_held: int) -> float | None:
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

            if not row or not row[0] or not row[1]:
                raise ValueError(f"Insufficient data for {symbol} to calculate chandelier stop")

            hh = float(row[0])

            atr = float(row[1])

            mult_val = self.config.get("chandelier_atr_mult")

            if mult_val is None:
                raise ValueError(
                    "CRITICAL: chandelier_atr_mult config missing. Cannot calculate chandelier trailing stop."
                )

            mult = float(mult_val)

            return round(hh - (mult * atr), 2)

    def _get_td_state(self, cur, symbol, current_date) -> dict[str, Any]:
        """Return full TD state dict (for both 9 and 13 detection).



        Fail-fast  - if TD Sequential cannot be computed, raises exception.

        TD Sequential is a required exit signal for positions.

        """

        sc = SignalComputer(self.config)

        td_state = sc.td_sequential(symbol, current_date)

        if not td_state:
            raise ValueError(f"TD Sequential calculation failed for {symbol}")

        return td_state

    def _is_minervini_break(self, cur, symbol: str, current_date, cur_price: float) -> bool:
        """Close < 50-DMA OR (close < EMA(21) AND volume > 50-day avg)."""

        cur.execute(
            """

            SELECT td.sma_50, td.ema_21,

                   (SELECT volume FROM price_daily p WHERE p.symbol = td.symbol AND p.date = td.date) AS vol,

                   (SELECT AVG(volume) FROM price_daily p

                     WHERE p.symbol = td.symbol AND p.date <= td.date

                       AND p.date >= td.date - INTERVAL '50 days') AS avg_vol_50

            FROM technical_data_daily td

            WHERE td.symbol = %s AND td.date <= %s

            ORDER BY td.date DESC LIMIT 1

            """,
            (symbol, current_date),
        )

        row = cur.fetchone()

        if row is None:
            return False

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

        if sma_50 and cur_price_decimal < sma_50 * Decimal("0.99"):
            return True

        # Break of EMA(21) on rising volume (institutional selling)

        ema_21_float = float(ema_21) if ema_21 else None

        if ema_21_float and cur_price < ema_21_float and avg_vol_50 > 0 and vol > avg_vol_50 * 1.15:
            return True

        return False

    def _check_volume_spike(self, cur, symbol: str, current_date, volume_multiplier: float) -> bool:
        """Check if today's volume is >= volume_multiplier * average volume."""

        cur.execute(
            """

            SELECT pd.volume,

                   (SELECT AVG(volume) FROM price_daily p

                    WHERE p.symbol = pd.symbol

                      AND p.date <= pd.date

                      AND p.date > pd.date - INTERVAL '50 days') AS avg_vol_50

            FROM price_daily pd

            WHERE pd.symbol = %s AND pd.date = %s

            """,
            (symbol, current_date),
        )

        row = cur.fetchone()

        if not row or row[0] is None or row[1] is None:
            raise ValueError(f"Volume data unavailable for {symbol} on {current_date}")

        today_vol = float(row[0])

        avg_vol = float(row[1])

        return today_vol >= avg_vol * volume_multiplier

    def _compute_gain_last_n_days(self, cur, symbol: str, current_date, n_days: int) -> float | None:
        """Compute % gain over the last N days (from close N days ago to current close)."""

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

        if not row or row[0] is None or row[1] is None:
            raise ValueError(f"Insufficient {n_days}-day price data for {symbol}")

        current = Decimal(str(row[0]))

        prior = Decimal(str(row[1]))

        if prior <= 0:
            raise ValueError(f"Invalid price data for {symbol}: prior close = {prior}")

        return float(((current - prior) / prior * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


if __name__ == "__main__":
    from algo.infrastructure import get_config

    config = get_config()

    engine = ExitEngine(config)

    exits = engine.check_and_execute_exits()

    logger.info(f"Exits executed: {exits}")
