#!/usr/bin/env python3
"""Shared "pure trail" exit-simulation primitives: hard stop -> breakeven floor ->
chandelier/21-EMA trail -> time exit (with O'Neil 8-week-rule extension), no T1/T2/T3
scale-out.

REAL-MONEY-READINESS FINDING (2026-09-10, financial-calculation-integrity re-audit): live
algo_config currently has `use_scale_out_targets=false` (migration 1273, seeded 2026-09-07
after `scripts/backtest_exit_strategy_comparison_20260907.py` found a pure trailing-stop exit
beat the T1/T2/T3 scale-out chain on mean R-multiple, geometric per-trade growth, and tail
capture across 471,972 paired trades, 2,885 symbols, 1962-2026 - see exit_position_context.py's
check_target_t1 docstring). That means the exit rules in THIS module - not the scale-out chain
- are what live actually runs today: hard stop, breakeven floor once price reaches
move_be_at_r, the chandelier/21-EMA trail once price reaches 1R, and a time exit at
max_hold_days (extended once via the 8-week rule if the trade showed an early 20%+ gain).

This module extracts those formulas (moved verbatim, not re-derived, from the already-
validated comparison script above - see its own docstring for the full backtest methodology)
into an importable form so `algo/backtest/run_backtest.py`'s standard CLI can simulate the
SAME exit rules against its own real entry/ranking signal list, not just the one-off
standalone comparison's separately-replayed technical-only entries. `run_backtest.py` was
previously the only place still describing this gap as fully open ("this backtest's EXIT logic
does not match live's... no live exit backtest coverage at all") - that was already stale by
the time it was written (the comparison script landed the same day), but the standard/
repeatable backtest CLI still could not simulate live's actual exit mechanics until now.

SCOPE (same as the comparison script - not a difference introduced here): TD Sequential,
RS-line-break, first-red-day, climax-exhaustion, distribution-day, and Minervini-break
(already disabled) are NOT simulated - they're secondary overlays on top of the mechanism this
module targets, not the mechanism itself, and faithfully replaying their stateful/market-wide
logic is a materially larger undertaking than this module's scope.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as _date
from typing import Any

import numpy as np

# Live exit-chain parameters (mirrors algo_config as of 2026-09-07 - see
# algo/infrastructure/config/trading_config.py / config_schema.py for where each of these
# lives in production, and exit_position_context.py's check_move_to_breakeven/
# check_chandelier_trail for the live formulas these mirror).
MOVE_BE_AT_R = 1.0
CHANDELIER_ATR_MULT = 3.0
SWITCH_TO_21EMA_AFTER_DAYS = 10
EIGHT_WEEK_RULE_THRESHOLD_PCT = 20.0
EIGHT_WEEK_RULE_WINDOW_DAYS = 21
EIGHT_WEEK_RULE_MAX_EXTENSION_DAYS = 56


def ema_of_window(closes_window: np.ndarray[Any, Any]) -> float:
    """Matches exit_engine.py's _chandelier_or_ema_stop 21-EMA branch exactly: seeds from the
    OLDEST close in a 30-bar trailing window (not a full-history recursive EMA), k=2/22."""
    k = 2.0 / 22.0
    ema = closes_window[0]
    for c in closes_window[1:]:
        ema = c * k + ema * (1 - k)
    return float(ema)


def chandelier_or_ema_stop(
    days_held: int, highs: np.ndarray[Any, Any], closes: np.ndarray[Any, Any], atr: np.ndarray[Any, Any], i: int
) -> float | None:
    """Mirrors exit_engine.py's _chandelier_or_ema_stop exactly: chandelier (highest-high
    over max(days_held,5) bars minus CHANDELIER_ATR_MULT x ATR) while
    days_held < SWITCH_TO_21EMA_AFTER_DAYS, then 0.99x a 30-bar-seeded 21-EMA of closes after
    that."""
    if days_held >= SWITCH_TO_21EMA_AFTER_DAYS:
        start = i - 29
        if start < 0:
            return None
        window = closes[start : i + 1]
        if len(window) < 21:
            return None
        return ema_of_window(window) * 0.99
    lookback = max(days_held, 5)
    start = max(0, i - lookback + 1)
    hh = highs[start : i + 1].max()
    cur_atr = atr[i]
    if math.isnan(cur_atr) or math.isnan(hh):
        return None
    return float(hh - CHANDELIER_ATR_MULT * cur_atr)


def eight_week_rule_active(closes: np.ndarray[Any, Any], entry_idx: int, days_held: int, entry_price: float) -> bool:
    """Mirrors exit_engine.py's _eight_week_rule_active: 20%+ gain within the first
    EIGHT_WEEK_RULE_WINDOW_DAYS days of the trade grants an extension."""
    if days_held < EIGHT_WEEK_RULE_WINDOW_DAYS:
        return False
    window_start = entry_idx
    window_end = min(entry_idx + EIGHT_WEEK_RULE_WINDOW_DAYS, entry_idx + days_held + 1)
    window = closes[window_start:window_end]
    if len(window) == 0:
        return False
    max_close = window.max()
    return bool(((max_close - entry_price) / entry_price * 100.0) >= EIGHT_WEEK_RULE_THRESHOLD_PCT)


@dataclass
class LiveTrailExitResult:
    """Outcome of walking a position forward under live's pure-trail exit rules."""

    exit_date: _date
    exit_price: float
    exit_reason: str  # "stop" | "time" | "still_open" (ran off the end of available history)
    days_held: int


def simulate_live_trail_exit(
    *,
    entry_idx: int,
    entry_price: float,
    init_stop: float,
    dates: np.ndarray[Any, Any],
    df_high: np.ndarray[Any, Any],
    df_low: np.ndarray[Any, Any],
    df_close: np.ndarray[Any, Any],
    df_atr: np.ndarray[Any, Any],
    max_hold_days: int,
    move_be_at_r: float = MOVE_BE_AT_R,
) -> LiveTrailExitResult:
    """Walk a position forward from entry_idx under live's actual (scale-out-disabled) exit
    chain: hard stop -> breakeven floor -> chandelier/21-EMA trail -> time exit (8-week-rule
    extension). Same rule order/formulas as
    backtest_exit_strategy_comparison_20260907.py's simulate_arm(scale_out=False) - kept
    separate from that function (rather than sharing one code path) because this one returns
    a concrete exit date/price for run_backtest.py's dollar-P&L accounting, not an R-multiple.

    `dates`/`df_high`/`df_low`/`df_close`/`df_atr` must be aligned numpy arrays (same length,
    same row order) covering at least from entry_idx to the end of the symbol's available
    history. init_stop must be entry_price's already-computed initial stop (the same basis
    run_backtest.py's own `stop_loss_pct`-derived stop_level uses for the "fixed" exit mode),
    so risk-per-share is internally consistent between the two exit modes.

    Fill prices are priced at the theoretical stop/close level (matching run_backtest.py's
    existing "fixed" mode convention - see its own INTRADAY RANGE DETECTION docstring note),
    not the exact worse price a real gap-through would produce.
    """
    risk = entry_price - init_stop
    if risk <= 0:
        raise ValueError(
            f"[LIVE_TRAIL] entry_price={entry_price} <= init_stop={init_stop} (non-positive risk). "
            "Cannot compute R-multiple-based exit rules."
        )
    n = len(df_close)
    active_stop = init_stop

    i = entry_idx
    days_held = 0
    while i < n:
        lo, cl = df_low[i], df_close[i]

        # 1. Hard stop-loss (checked against intrabar low)
        if lo <= active_stop:
            return LiveTrailExitResult(
                exit_date=dates[i], exit_price=active_stop, exit_reason="stop", days_held=days_held
            )

        r_close = (cl - entry_price) / risk

        # 2. Breakeven floor
        if r_close >= move_be_at_r and active_stop < entry_price:
            active_stop = entry_price

        # 3. Chandelier / 21-EMA trail (gated on r_close >= 1R, matches production)
        if r_close >= 1.0:
            candidate = chandelier_or_ema_stop(days_held, df_high, df_close, df_atr, i)
            if candidate is not None and candidate > active_stop:
                active_stop = min(candidate, cl - 0.01) if candidate >= cl else candidate

        # 4. Time-based exit (with O'Neil 8-week-rule extension)
        if days_held >= max_hold_days:
            extended = eight_week_rule_active(df_close, entry_idx, days_held, entry_price)
            if not (extended and days_held < EIGHT_WEEK_RULE_MAX_EXTENSION_DAYS):
                return LiveTrailExitResult(
                    exit_date=dates[i], exit_price=float(cl), exit_reason="time", days_held=days_held
                )

        i += 1
        days_held += 1

    # Ran off the end of available history before resolving - caller must treat this position
    # as still open (e.g. close it at the final simulated date's price, matching
    # run_backtest.py's existing end-of-backtest handling for any other still-open position).
    return LiveTrailExitResult(
        exit_date=dates[n - 1],
        exit_price=float(df_close[n - 1]),
        exit_reason="still_open",
        days_held=days_held,
    )
