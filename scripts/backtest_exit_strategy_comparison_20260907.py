#!/usr/bin/env python3
"""
STANDALONE, READ-ONLY historical backtest: T1/T2/T3 scale-out vs. pure trailing-stop exits.

NOT a production loader - never scheduled, never called by orchestrator/loaders. Only reads
price_daily (already-loaded history). Writes its own output to local CSV files only under
scripts/output/ - never touches any production table. Matches the safety pattern established
by scripts/backtest_regime_reconstruction.py (2026-09-04).

WHY THIS EXISTS (2026-09-07 exit-strategy literature review, goal session): a prior review of
algo/trading/exit_strategies.py against trading literature found the T1/T2/T3 partial-profit-
taking design (sell 50%/25%/25% at fixed R-multiples) to be the one place trend-following
literature is fairly consistent AGAINST the current approach - scaling out lowers blended
expectancy vs. a pure trail by capping the fat-tail winners a trend system's edge depends on.
That review could not validate/invalidate this against our own data because buy_sell_daily
(the live production entry-signal table) is only ~83 days deep - see
tests/unit/test_regime_adaptive_exits_backtest_infeasible_20260825.py, which hit the identical
blocker for regime-adaptive exits. The fix there (backtest_regime_reconstruction.py) was to
recompute the real scoring logic from raw price_daily history instead of trusting the shallow
production snapshot. The same fix applies here: the actual BUY entry trigger in
algo/signals/buy_signal_generator.py is 100% price-technical (swing-pivot breakout above a
rising 50-day SMA) - no fundamentals dependency at all - so it can be replayed for decades
directly from price_daily, which goes back to 1962 for many symbols.

SCOPE / WHAT THIS DOES NOT TEST (be honest about the limitation, don't over-claim):
  - Entries use ONLY the price-technical BUY trigger (confirmed swing-high breakout above a
    rising 50-day SMA, per buy_signal_generator.py's _generate_signal/_find_confirmed_swing_
    high). The real production system ALSO screens candidates by quality/growth/value pillar
    scores before taking a signal - that fundamentals-dependent filtering cannot be replayed
    decades back (same blocker as regime-adaptive exits) and is NOT simulated here. This
    backtest answers "given a technically-valid trend entry, which exit design performs
    better" - not "what would our full system's exact historical trade list have returned."
  - Only the exit rules central to the scale-out-vs-trail question are simulated: hard stop-
    loss (swing-low pivot), the breakeven floor (move_be_at_r), T1/T2/T3 targets (Arm A only),
    and the chandelier/21-EMA trail. TD Sequential, RS-line-break, first-red-day, climax-
    exhaustion, distribution-day, and Minervini-break (already disabled, 0% win rate per prior
    backtest) are excluded from BOTH arms - they're secondary overlays, not the mechanism in
    question, and faithfully replaying them (TD Sequential's stateful count, sector-relative RS
    lines, market-wide distribution-day counts) is a materially larger undertaking than this
    focused comparison needs.
  - No portfolio capital constraints/position sizing/concurrent-position limits are modeled.
    Each entry is treated as an independent, isolated single-position trial (unlimited
    capital, one slot). This is the right level of rigor for the literature question at hand
    (per-trade expectancy and tail-capture), which is about exit mechanics, not capital
    allocation. Trades are still non-overlapping PER SYMBOL (see pairing method below).

METHOD (paired trial design - the statistically strong part of this): for each symbol, walk
forward with a single flat/in-position state machine using the real production entry trigger.
On each qualifying entry (fill at next day's OPEN, avoiding same-bar lookahead; initial stop =
confirmed swing-low pivot, or a simple relaxed fallback - trailing 20-day low - if no confirmed
low exists yet), simulate BOTH exit arms forward from the IDENTICAL entry/stop against the
IDENTICAL price path:
  Arm A ("current system"): hard stop -> breakeven floor (move_be_at_r) -> T1(2.5R, 50%) ->
    T2(3R, 50% of remainder) -> T3(4R, 100% of remainder) -> chandelier/21-EMA trail -> time
    exit (max_hold_days, with O'Neil 8-week-rule extension). R-multiples use the LIVE
    t1_target_r_multiple=2.5 (not the 1.5 documented default - see
    t1_target_r_multiple_drift_open_20260907 memory) since that's what's actually running.
  Arm B ("pure trail"): hard stop -> breakeven floor -> chandelier/21-EMA trail -> time exit.
    No partial scale-out; full position held until stopped out or time-exited.
Both arms' exit-price/date logic matches exit_position_context.py's actual formulas (same
R-multiple math, same chandelier ATR/EMA formulas via loaders/technical_indicators.py's
compute_atr, same 8-week-rule window). The symbol becomes flat again only once BOTH arms have
fully resolved that trade, guaranteeing no overlap and a clean paired (R_A, R_B) sample per
entry - enables a paired significance test (bootstrap CI on mean(R_A - R_B), not just comparing
two unpaired distributions).

Splits: price_daily stores RAW (unadjusted) prices - reuses
loaders/technical_indicators.py's detect_and_adjust_splits() per symbol before computing
anything, exactly like production loaders do, so a real split doesn't masquerade as a -50%
crash and corrupt pivot/stop/R-multiple math.

Output: scripts/output/exit_strategy_comparison_trades_<timestamp>.csv (per-trade detail) and
a printed summary comparison. Read-only DB access, local file output only.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

from loaders.technical_indicators import compute_atr, detect_and_adjust_splits

load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")

CONN = psycopg2.connect(
    host=os.environ["DB_HOST"],
    dbname=os.environ["DB_NAME"],
    user=os.environ.get("DB_USER", "postgres"),
    password=os.environ["DB_PASSWORD"],
    port=os.environ.get("DB_PORT", 5432),
)
CONN.set_session(readonly=True)

# ---- Live exit-chain parameters (mirrors algo_config as of 2026-09-07 - see
# algo/infrastructure/config/trading_config.py / config_schema.py / the memory files cited
# above for where each of these lives in production) ----
T1_R_MULTIPLE = 2.5  # LIVE value (not the 1.5 schema default - see memory)
T2_R_MULTIPLE = 3.0
T3_R_MULTIPLE = 4.0
MOVE_BE_AT_R = 1.0
CHANDELIER_ATR_MULT = 3.0
SWITCH_TO_21EMA_AFTER_DAYS = 10
MAX_HOLD_DAYS = 20
EIGHT_WEEK_RULE_THRESHOLD_PCT = 20.0
EIGHT_WEEK_RULE_WINDOW_DAYS = 21
EIGHT_WEEK_RULE_MAX_EXTENSION_DAYS = 56
PIVOT_BARS = 3  # left/right confirmation bars, matches buy_signal_generator.py's pivothigh(3,3)
MIN_RISK_PCT_FLOOR = 1.0  # exclude near-zero-risk-denominator entries (see run_symbol)
MAX_RISK_PCT_CEILING = 50.0  # exclude extreme-geometry outliers (see run_symbol)
ABS_R_SANITY_CEILING = 100.0  # exclude implausible-magnitude trials, usually unadjusted splits


@dataclass
class TradeOutcome:
    symbol: str
    entry_date: _date
    exit_date: _date
    entry_price: float
    init_stop: float
    days_held: int
    realized_r: float
    win: bool
    exit_reason: str


@dataclass
class SimState:
    """Mutable per-arm simulation state for one open trade."""

    active_stop: float
    remaining_fraction: float = 1.0
    realized_r: float = 0.0
    target_hits: int = 0
    closed: bool = False
    exit_date: _date | None = None
    exit_reason: str = ""
    days_held: int = 0


def get_universe(min_years: float = 10.0, sample: int | None = None, seed: int = 42) -> list[str]:
    cur = CONN.cursor()
    cur.execute(
        """
        SELECT symbol, MIN(date) AS first_date, MAX(date) AS last_date, COUNT(*) AS n
        FROM price_daily
        WHERE close IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND open IS NOT NULL
        GROUP BY symbol
        HAVING MAX(date) - MIN(date) >= (%s * 365.25)::int
           AND COUNT(*) >= (%s * 200)::int
        """,
        (min_years, min_years),
    )
    rows = cur.fetchall()
    symbols = [r[0] for r in rows if not r[0].startswith("^") and len(r[0]) <= 6]
    symbols.sort()
    print(f"Universe: {len(symbols)} symbols with >= {min_years:.0f}yr price_daily history")
    if sample is not None and sample < len(symbols):
        rng = random.Random(seed)
        symbols = rng.sample(symbols, sample)
        symbols.sort()
        print(f"Sampled {len(symbols)} symbols (seed={seed})")
    return symbols


def load_symbol_frame(symbol: str) -> pd.DataFrame | None:
    cur = CONN.cursor()
    cur.execute(
        """
        SELECT date, open, high, low, close, volume
        FROM price_daily
        WHERE symbol = %s AND close IS NOT NULL AND high IS NOT NULL
              AND low IS NOT NULL AND open IS NOT NULL
        ORDER BY date
        """,
        (symbol,),
    )
    rows = cur.fetchall()
    if len(rows) < 300:
        return None
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df = detect_and_adjust_splits(df)
    # Defensive: a bad tick (zero/negative price) breaks every ratio/R-multiple computation
    # downstream - drop rows that couldn't be real trading prices rather than let a single
    # corrupt row silently poison an entire symbol's pivot/stop history.
    df = df[(df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0)].reset_index(drop=True)
    if len(df) < 300:
        return None
    df["sma_50"] = df["close"].rolling(50).mean()
    df["atr_14"] = compute_atr(df["high"], df["low"], df["close"], period=14)
    return df


def find_confirmed_pivots(highs: np.ndarray, lows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Efficient O(n) equivalent of buy_signal_generator.py's _find_confirmed_swing_high/_low:
    a bar j is a confirmed pivot high/low once PIVOT_BARS bars on each side confirm it (visible
    starting bar j+PIVOT_BARS, matching Pine's 3-bars-later confirmation lag). Returns, for
    each bar i, the MOST RECENT confirmed pivot value known as of bar i (None/NaN if none yet)
    - i.e. what buy_signal_generator.py's O(n^2) unbounded search would return, computed in a
    single forward pass instead.
    """
    n = len(highs)
    last_high = np.full(n, np.nan)
    last_low = np.full(n, np.nan)
    cur_high = math.nan
    cur_low = math.nan
    for i in range(n):
        j = i - PIVOT_BARS
        if j >= PIVOT_BARS:
            left = highs[j - PIVOT_BARS : j]
            right = highs[j + 1 : j + 1 + PIVOT_BARS]
            if len(left) == PIVOT_BARS and len(right) == PIVOT_BARS:
                cand = highs[j]
                if cand > left.max() and cand > right.max():
                    cur_high = cand
            left_l = lows[j - PIVOT_BARS : j]
            right_l = lows[j + 1 : j + 1 + PIVOT_BARS]
            if len(left_l) == PIVOT_BARS and len(right_l) == PIVOT_BARS:
                cand_l = lows[j]
                if cand_l < left_l.min() and cand_l < right_l.min():
                    cur_low = cand_l
        last_high[i] = cur_high
        last_low[i] = cur_low
    return last_high, last_low


def ema_of_window(closes_window: np.ndarray) -> float:
    """Matches exit_engine.py's _chandelier_or_ema_stop 21-EMA branch exactly: seeds from the
    OLDEST close in a 30-bar trailing window (not a full-history recursive EMA), k=2/22."""
    k = 2.0 / 22.0
    ema = closes_window[0]
    for c in closes_window[1:]:
        ema = c * k + ema * (1 - k)
    return ema


def chandelier_or_ema_stop(
    days_held: int, highs: np.ndarray, closes: np.ndarray, atr: np.ndarray, i: int
) -> float | None:
    """Mirrors exit_engine.py's _chandelier_or_ema_stop exactly (see that function's
    docstring/body): chandelier (highest-high over max(days_held,5) bars minus
    CHANDELIER_ATR_MULT x ATR) while days_held < SWITCH_TO_21EMA_AFTER_DAYS, then 0.99x a
    30-bar-seeded 21-EMA of closes after that."""
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
    return hh - CHANDELIER_ATR_MULT * cur_atr


def eight_week_rule_active(closes: np.ndarray, entry_idx: int, days_held: int, entry_price: float) -> bool:
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
    return ((max_close - entry_price) / entry_price * 100.0) >= EIGHT_WEEK_RULE_THRESHOLD_PCT


def simulate_arm(
    *,
    scale_out: bool,
    entry_idx: int,
    entry_price: float,
    init_stop: float,
    df_high: np.ndarray,
    df_low: np.ndarray,
    df_close: np.ndarray,
    df_atr: np.ndarray,
) -> tuple[float, int, int, str]:
    """Simulate one exit arm forward from entry_idx (the fill bar) to resolution.
    Returns (realized_r, exit_idx, days_held_at_exit, exit_reason)."""
    risk = entry_price - init_stop
    n = len(df_close)
    state = SimState(active_stop=init_stop)
    t1_price = entry_price + T1_R_MULTIPLE * risk
    t2_price = entry_price + T2_R_MULTIPLE * risk
    t3_price = entry_price + T3_R_MULTIPLE * risk

    i = entry_idx
    days_held = 0
    while i < n:
        lo, hi, cl = df_low[i], df_high[i], df_close[i]

        # 1. Hard stop-loss (checked against intrabar low, most realistic trigger point)
        if lo <= state.active_stop:
            r_at_exit = (state.active_stop - entry_price) / risk
            state.realized_r += state.remaining_fraction * r_at_exit
            return state.realized_r, i, days_held, "stop"

        r_close = (cl - entry_price) / risk

        # 2. Breakeven floor
        if r_close >= MOVE_BE_AT_R and state.active_stop < entry_price:
            state.active_stop = entry_price

        # 3/4/5. T1/T2/T3 scale-out (Arm A only)
        if scale_out:
            if state.target_hits == 0 and hi >= t1_price:
                sold = state.remaining_fraction * 0.5
                r_at_t1 = (t1_price - entry_price) / risk
                state.realized_r += sold * r_at_t1
                state.remaining_fraction -= sold
                state.active_stop = max(state.active_stop, entry_price)
                state.target_hits = 1
            elif state.target_hits == 1 and hi >= t2_price:
                sold = state.remaining_fraction * 0.5
                r_at_t2 = (t2_price - entry_price) / risk
                state.realized_r += sold * r_at_t2
                state.remaining_fraction -= sold
                state.active_stop = max(state.active_stop, t1_price)
                state.target_hits = 2
            elif state.target_hits == 2 and hi >= t3_price:
                sold = state.remaining_fraction
                r_at_t3 = (t3_price - entry_price) / risk
                state.realized_r += sold * r_at_t3
                state.remaining_fraction = 0.0
                return state.realized_r, i, days_held, "target_3"

        # 6. Chandelier / 21-EMA trail (gated on r_close >= 1R, matches production)
        if r_close >= 1.0:
            candidate = chandelier_or_ema_stop(days_held, df_high, df_close, df_atr, i)
            if candidate is not None and candidate > state.active_stop:
                state.active_stop = min(candidate, cl - 0.01) if candidate >= cl else candidate

        # 7. Time-based exit (with O'Neil 8-week-rule extension)
        if days_held >= MAX_HOLD_DAYS:
            extended = eight_week_rule_active(df_close, entry_idx, days_held, entry_price)
            if not (extended and days_held < EIGHT_WEEK_RULE_MAX_EXTENSION_DAYS):
                r_at_time = (cl - entry_price) / risk
                state.realized_r += state.remaining_fraction * r_at_time
                return state.realized_r, i, days_held, "time"

        i += 1
        days_held += 1

    # Ran off the end of available history before resolving - censor this trade (caller drops it).
    r_at_end = (df_close[n - 1] - entry_price) / risk
    return state.realized_r + state.remaining_fraction * r_at_end, n - 1, days_held, "censored_end_of_data"


def run_symbol(symbol: str, df: pd.DataFrame) -> list[tuple[TradeOutcome, TradeOutcome]]:
    dates: list[_date] = list(df["date"])
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    opens = df["open"].to_numpy()
    sma50 = df["sma_50"].to_numpy()
    atr = df["atr_14"].to_numpy()
    n = len(df)

    piv_high, piv_low = find_confirmed_pivots(highs, lows)

    results: list[tuple[TradeOutcome, TradeOutcome]] = []
    # resume_idx tracks "flat again" state: after a paired trial, the symbol is not eligible
    # for a new entry until BOTH arms have fully resolved (see module docstring's pairing
    # method) - this single index replaces a simple in_position flag.
    resume_idx = 0
    i = 0
    while i < n - 1:  # need at least one more bar to fill the entry
        if i < resume_idx:
            i += 1
            continue
        if not math.isnan(sma50[i]) and not math.isnan(piv_high[i]):
            csh = piv_high[i]
            if highs[i] > csh and csh > sma50[i]:
                # Entry fills at NEXT bar's open (1-day lag, matches production/run_backtest.py
                # convention, avoids same-bar lookahead).
                entry_idx = i + 1
                entry_price = opens[entry_idx]
                if not math.isnan(piv_low[i]) and piv_low[i] < entry_price:
                    init_stop = piv_low[i]
                else:
                    # Relaxed fallback (no confirmed low yet): trailing 20-bar low, matching
                    # _find_swing_low's real-stop-needed intent without its full tiered search.
                    lb_start = max(0, i - 19)
                    init_stop = float(lows[lb_start : i + 1].min())
                if entry_price <= 0:
                    i += 1
                    continue
                risk_pct = (entry_price - init_stop) / entry_price * 100.0
                # MIN_RISK_PCT_FLOOR guards against near-zero risk denominators: a swing-low
                # pivot sitting within noise/floating-point distance of entry_price (confirmed
                # live in an early run of this script - OMEX 2001-09-10 had init_stop and
                # entry_price differing by ~1e-14, a bit-representation artifact of the two
                # values coming through different pandas Series - not a real 0%-risk trade)
                # makes R = (price_move)/risk blow up to nonsensical magnitudes (a single such
                # trade produced a "mean R" in the hundreds of millions across 476,899 trades
                # in that run). MAX_RISK_PCT_CEILING excludes penny-stock/low-liquidity
                # geometries with stops 50%+ away from entry - not a claim about real
                # production behavior (max_stop_distance_pct=12.0% exists in algo_config but,
                # confirmed via grep, is not actually wired to any entry gate today), just a
                # sanity bound so a handful of extreme-geometry outliers can't dominate half a
                # million trades' worth of aggregate statistics.
                if risk_pct < MIN_RISK_PCT_FLOOR or risk_pct > MAX_RISK_PCT_CEILING:
                    i += 1
                    continue  # degenerate or extreme-geometry entry, skip

                arm_a_r, arm_a_idx, arm_a_days, arm_a_reason = simulate_arm(
                    scale_out=True,
                    entry_idx=entry_idx,
                    entry_price=entry_price,
                    init_stop=init_stop,
                    df_high=highs,
                    df_low=lows,
                    df_close=closes,
                    df_atr=atr,
                )
                arm_b_r, arm_b_idx, arm_b_days, arm_b_reason = simulate_arm(
                    scale_out=False,
                    entry_idx=entry_idx,
                    entry_price=entry_price,
                    init_stop=init_stop,
                    df_high=highs,
                    df_low=lows,
                    df_close=closes,
                    df_atr=atr,
                )
                if arm_a_reason == "censored_end_of_data" or arm_b_reason == "censored_end_of_data":
                    break  # can't pair a censored trial fairly - stop scanning this symbol

                # ABS_R_SANITY_CEILING: excludes the whole paired trial (not just clips one
                # arm) when either side produces an implausible R-multiple. Confirmed live in
                # an earlier run: AEHL 2020-08-18 produced arm_b_r=7085 in an 11-day hold - a
                # trailed stop that far above entry in 11 days is not a real price move, it's
                # an unadjusted corporate action (reverse split) slipping past
                # detect_and_adjust_splits()'s known-ratio matching (that function's own
                # docstring flags this exact limitation). Investigating every microcap's
                # corporate-action history is out of scope for this focused exit-mechanics
                # comparison (see module docstring's scope note) - excluding the rare
                # implausible-magnitude trial is the defensible tradeoff, and dropping the
                # PAIR (not clipping) keeps the paired design's integrity intact.
                if abs(arm_a_r) > ABS_R_SANITY_CEILING or abs(arm_b_r) > ABS_R_SANITY_CEILING:
                    resume_idx = max(arm_a_idx, arm_b_idx) + 1
                    i = resume_idx
                    continue

                results.append(
                    (
                        TradeOutcome(
                            symbol,
                            dates[entry_idx],
                            dates[arm_a_idx],
                            entry_price,
                            init_stop,
                            arm_a_days,
                            arm_a_r,
                            arm_a_r > 0,
                            arm_a_reason,
                        ),
                        TradeOutcome(
                            symbol,
                            dates[entry_idx],
                            dates[arm_b_idx],
                            entry_price,
                            init_stop,
                            arm_b_days,
                            arm_b_r,
                            arm_b_r > 0,
                            arm_b_reason,
                        ),
                    )
                )
                resume_idx = max(arm_a_idx, arm_b_idx) + 1
                i = resume_idx
                continue
        i += 1
    return results


def bootstrap_ci(diffs: list[float], n_boot: int = 5000, seed: int = 7) -> tuple[float, float, float]:
    rng = random.Random(seed)
    n = len(diffs)
    mean_diff = sum(diffs) / n
    boot_means = []
    for _ in range(n_boot):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    lo = boot_means[int(0.025 * n_boot)]
    hi = boot_means[int(0.975 * n_boot)]
    return mean_diff, lo, hi


def summarize(label: str, trades: list[TradeOutcome]) -> dict:
    rs = [t.realized_r for t in trades]
    n = len(rs)
    wins = [r for r in rs if r > 0]
    mean_r = sum(rs) / n
    std_r = (sum((r - mean_r) ** 2 for r in rs) / (n - 1)) ** 0.5 if n > 1 else 0.0
    win_rate = len(wins) / n
    median_r = float(np.median(rs))
    p99_r = float(np.percentile(rs, 99))
    p1_r = float(np.percentile(rs, 1))
    sorted_rs = sorted(rs, reverse=True)
    top_decile_n = max(1, n // 10)
    total_positive = sum(r for r in rs if r > 0)
    top_decile_positive = sum(r for r in sorted_rs[:top_decile_n] if r > 0)
    tail_share = (top_decile_positive / total_positive) if total_positive > 0 else 0.0

    # Geometric per-trade growth rate at a fixed 1% account risk per trade - NOT a sequential
    # single-account equity curve (deliberately dropped an earlier version of this metric that
    # naively chrono-sorted and sequentially compounded all trades across all symbols onto one
    # account: with thousands of symbols' trades genuinely overlapping in time, that treats
    # positions that would actually run CONCURRENTLY as if only one could ever be open,
    # compounding the same capital hundreds of times over on the same calendar days and
    # producing meaningless multi-quintillion-percent "returns" - a modeling artifact of the
    # no-portfolio-constraints scope (see module docstring), not a real result. The geometric
    # mean of each trade's own (1+0.01*R) multiplier avoids that: it's a property of the trade
    # distribution alone (order/overlap-independent) and is what actually governs long-run
    # compounding if a fixed fraction of capital is risked per trade, which the arithmetic mean
    # R above does not capture (variance drag: a wider R distribution compounds worse per unit
    # of mean R than a narrower one at the same mean).
    log_growth = sum(math.log1p(0.01 * r) for r in rs) / n
    geo_growth_pct = (math.exp(log_growth) - 1) * 100

    print(f"\n=== {label} (n={n} trades) ===")
    print(f"  Mean R-multiple:      {mean_r:+.3f}")
    print(f"  Median R-multiple:    {median_r:+.3f}")
    print(f"  1st/99th pctile R:    {p1_r:+.2f} / {p99_r:+.2f}")
    print(f"  Std dev R:            {std_r:.3f}")
    print(f"  Win rate:             {win_rate:.1%}")
    print(f"  Top-decile tail share of total profit: {tail_share:.1%}")
    print(f"  Geometric growth/trade (1% risk/trade, order-independent): {geo_growth_pct:+.3f}%")
    return {
        "label": label,
        "n": n,
        "mean_r": mean_r,
        "median_r": median_r,
        "std_r": std_r,
        "win_rate": win_rate,
        "tail_share": tail_share,
        "geo_growth_pct_per_trade": geo_growth_pct,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=600, help="Number of symbols to sample (default 600)")
    parser.add_argument("--full", action="store_true", help="Run the full 10+yr universe, ignore --sample")
    parser.add_argument("--min-years", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    symbols = get_universe(min_years=args.min_years, sample=None if args.full else args.sample, seed=args.seed)

    all_pairs: list[tuple[TradeOutcome, TradeOutcome]] = []
    processed = 0
    for sym in symbols:
        df = load_symbol_frame(sym)
        if df is None:
            continue
        try:
            pairs = run_symbol(sym, df)
        except Exception as e:
            print(f"  [WARN] {sym}: {e}", file=sys.stderr)
            continue
        all_pairs.extend(pairs)
        processed += 1
        if processed % 100 == 0:
            print(f"  ...processed {processed}/{len(symbols)} symbols, {len(all_pairs)} paired trades so far")

    print(f"\nProcessed {processed} symbols, {len(all_pairs)} paired trades total.")
    if not all_pairs:
        print("No trades generated - nothing to compare.")
        return

    arm_a_trades = [p[0] for p in all_pairs]
    arm_b_trades = [p[1] for p in all_pairs]

    summarize("Arm A: current system (T1/T2/T3 scale-out + chandelier)", arm_a_trades)
    summarize("Arm B: pure trail (chandelier only, no scale-out)", arm_b_trades)

    diffs = [p[0].realized_r - p[1].realized_r for p in all_pairs]
    mean_diff, ci_lo, ci_hi = bootstrap_ci(diffs)
    print(f"\n=== Paired comparison (Arm A - Arm B), n={len(diffs)} ===")
    print(f"  Mean R difference:     {mean_diff:+.4f}")
    print(f"  95% bootstrap CI:      [{ci_lo:+.4f}, {ci_hi:+.4f}]")
    if ci_lo > 0:
        print("  => Arm A (scale-out) significantly BETTER mean R-multiple.")
    elif ci_hi < 0:
        print("  => Arm B (pure trail) significantly BETTER mean R-multiple.")
    else:
        print("  => No statistically significant difference in mean R-multiple.")

    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(exist_ok=True)
    ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"exit_strategy_comparison_trades_{ts}.csv"
    rows = []
    for a, b in all_pairs:
        rows.append(
            {
                "symbol": a.symbol,
                "entry_date": a.entry_date,
                "entry_price": a.entry_price,
                "init_stop": a.init_stop,
                "arm_a_exit_date": a.exit_date,
                "arm_a_days_held": a.days_held,
                "arm_a_r": a.realized_r,
                "arm_a_reason": a.exit_reason,
                "arm_b_exit_date": b.exit_date,
                "arm_b_days_held": b.days_held,
                "arm_b_r": b.realized_r,
                "arm_b_reason": b.exit_reason,
            }
        )
    pd.DataFrame(rows).to_csv(out_path, index=False)
    print(f"\nWrote {len(rows)} paired trades to {out_path}")


if __name__ == "__main__":
    main()
