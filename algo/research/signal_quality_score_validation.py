#!/usr/bin/env python3
"""
Permanent, re-runnable validation harness for `signal_quality_score` (loaders/signal_quality_scorer.py's
COMPONENT_MAXES, live Phase 8 entry gate via `min_signal_quality_score`).

Built 2026-08-26 to close a real gap found in [[signal_quality_score_pooled_check_no_predictive_power_found_20260825]]:
unlike stock_scores' 6 pillars (which each got a dedicated `algo/research/fama_macbeth_*.py` harness during the
2026-08-25 audit), this score - which directly gates real trade entries - had never had ANY dedicated validation
script, only a one-off ad hoc analysis whose numbers live only in a memory file. This script makes that check a
permanent, checked-in, re-runnable tool instead of something that has to be redone from scratch by hand every time
someone wants to know whether the live entry gate is actually working.

Methodology note (why this is NOT a Fama-MacBeth harness like the stock_scores factors): `buy_sell_daily` only has
~2.5 months of history as of 2026-08-26 (2026-06-12 onward) - nowhere near enough distinct calendar months for a
real monthly cross-sectional regression (FM needs many independent months; this has at most ~2-3). This script
instead runs the same pooled cross-sectional check the original one-off analysis used, with the same explicit
overstated-significance caveat (pooled panels double-count within-month correlation), PLUS a split-sample
robustness check and an explicit, hard-coded "insufficient history" gate that refuses to claim robustness until
enough independent months exist. Re-run this exact script (no changes needed) as `buy_sell_daily` accumulates more
history - once MIN_ROBUST_MONTHS worth of independent months exist, its own output will say so.

Usage:
    python -m algo.research.signal_quality_score_validation [--start-date DATE] [--horizons 5,10,20]

FORMULA-REGIME NOTE (found 2026-08-26, re-auditing the original 2026-08-25 finding): commit
`a9671ba8a` (landed 2026-08-20) fixed Phase 7's live intraday path from an independently
reimplemented, unweighted 3-of-7-component formula to the single shared, weighted
compute_signal_quality_components() also used by the batch loader - i.e. `signal_quality_score`
values before 2026-08-20 and on/after it are NOT the same formula. As of 2026-08-26, ~94% of
buy_sell_daily's BUY rows with a score predate that fix. The default --start-date is therefore
2026-08-20 (the fix's landing date), NOT the earliest available history - pooling pre-fix rows
with post-fix rows would silently average across two different scoring formulas and produce a
number that doesn't describe the formula actually gating trades today. Pass an earlier
--start-date explicitly only if you specifically want the old-formula regime (e.g. to compare
the two eras), not as a default.
"""

import argparse
import logging

import numpy as np
import pandas as pd

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

# Below this many distinct calendar months with a meaningful signal count, treat any correlation
# here as directional noise, not a real result - matches the "6-12 months" bar the original
# one-off finding set before this should be treated as real.
MIN_ROBUST_MONTHS = 6
MIN_SIGNALS_PER_MONTH = 30


def fetch_buy_signals_with_forward_returns(start_date: str, horizons: list[int]) -> pd.DataFrame:
    """One row per live BUY signal with signal_quality_score and forward N-trading-day returns,
    plus SPY's own contemporaneous forward return for the same signal date (like-for-like
    market-adjusted comparison, not just 'the market was up that quarter')."""
    lead_cols = ", ".join(f"LEAD(px, {h}) OVER (PARTITION BY symbol ORDER BY date) AS px_fwd{h}" for h in horizons)
    sql = f"""
        WITH px AS (
            SELECT symbol, date, COALESCE(adj_close, close) AS px
            FROM price_daily
            WHERE COALESCE(data_unavailable, false) = false AND date >= %(start_date)s
        ),
        px_fwd AS (
            SELECT symbol, date, px, {lead_cols}
            FROM px
        )
        SELECT b.symbol, b.date, b.signal_quality_score,
               f.px AS entry_px, {", ".join(f"f.px_fwd{h}" for h in horizons)},
               {", ".join(f"spy.px_fwd{h} AS spy_px_fwd{h}" for h in horizons)}, spy.px AS spy_entry_px
        FROM buy_sell_daily b
        JOIN px_fwd f ON f.symbol = b.symbol AND f.date = b.date
        JOIN px_fwd spy ON spy.symbol = 'SPY' AND spy.date = b.date
        WHERE b.signal = 'BUY' AND b.signal_quality_score IS NOT NULL
          AND b.date >= %(start_date)s
        ORDER BY b.date
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql, {"start_date": start_date})
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    numeric_cols = [c for c in df.columns if c not in ("symbol", "date")]
    for c in numeric_cols:
        df[c] = df[c].astype(float)
    for h in horizons:
        df[f"fwd_ret_{h}"] = df[f"px_fwd{h}"] / df["entry_px"] - 1.0
        df[f"spy_fwd_ret_{h}"] = df[f"spy_px_fwd{h}"] / df["spy_entry_px"] - 1.0
    return df


def _pooled_correlations(df: pd.DataFrame, horizon: int) -> tuple[float, float, int]:
    sub = df[["signal_quality_score", f"fwd_ret_{horizon}"]].dropna()
    if len(sub) < 10:
        return float("nan"), float("nan"), len(sub)
    pearson = sub["signal_quality_score"].corr(sub[f"fwd_ret_{horizon}"], method="pearson")
    spearman = sub["signal_quality_score"].corr(sub[f"fwd_ret_{horizon}"], method="spearman")
    return pearson, spearman, len(sub)


def _quintile_breakdown(df: pd.DataFrame, horizon: int) -> pd.DataFrame | None:
    """None (not an empty DataFrame) signals 'not enough resolved signals yet' - distinct from
    a genuine zero-variance/degenerate result, so callers can print a clear reason instead of
    qcut's opaque IndexError on an empty array (hit 2026-08-26 re-running this post the
    formula-unification default start-date change: horizons longer than the elapsed calendar
    time since the fix landed have literally zero rows with a resolved forward return yet)."""
    sub = df[["signal_quality_score", f"fwd_ret_{horizon}"]].dropna()
    if len(sub) < 10:
        return None
    sub = sub.assign(quintile=pd.qcut(sub["signal_quality_score"], 5, labels=False, duplicates="drop"))
    return sub.groupby("quintile")[f"fwd_ret_{horizon}"].agg(["mean", "count"])


def _split_sample_check(df: pd.DataFrame, horizon: int) -> tuple[float, float]:
    """First-half vs second-half (by date) pooled Pearson correlation - same robustness check
    already applied to every stock_scores pillar re-audit this codebase has done."""
    dates = df["date"].sort_values()
    midpoint = dates.iloc[len(dates) // 2]
    first_half = df[df["date"] < midpoint]
    second_half = df[df["date"] >= midpoint]
    r1, _, _ = _pooled_correlations(first_half, horizon)
    r2, _, _ = _pooled_correlations(second_half, horizon)
    return r1, r2


def run(start_date: str, horizons: list[int]) -> None:
    logger.info(f"Pulling live BUY signals with signal_quality_score from {start_date} onward")
    df = fetch_buy_signals_with_forward_returns(start_date, horizons)
    print(f"Live BUY signals with signal_quality_score: {len(df)}")
    if df.empty:
        print("No signals found in range - nothing to validate.")
        return

    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M")
    month_counts = df.groupby("month").size()
    robust_months = (month_counts >= MIN_SIGNALS_PER_MONTH).sum()
    print(f"Distinct months with >= {MIN_SIGNALS_PER_MONTH} signals: {robust_months} ({dict(month_counts)})\n")

    if robust_months < MIN_ROBUST_MONTHS:
        print(
            f"*** INSUFFICIENT HISTORY: only {robust_months} qualifying month(s), need "
            f"{MIN_ROBUST_MONTHS}+ before treating any correlation below as a real, actionable result. ***\n"
            "Do NOT change COMPONENT_MAXES or min_signal_quality_score off this output alone - re-run this\n"
            "exact script once buy_sell_daily has accumulated enough history.\n"
        )

    for h in horizons:
        pearson, spearman, n = _pooled_correlations(df, h)
        print(f"=== {h}-day forward return (n={n}) ===")
        if n < 10:
            print(f"  *** Fewer than 10 signals have a resolved {h}-day forward return yet - skipping. ***\n")
            continue
        print(f"  Pooled Pearson corr(signal_quality_score, fwd_ret): {pearson:+.4f}")
        print(f"  Pooled Spearman corr:                               {spearman:+.4f}")

        quint = _quintile_breakdown(df, h)
        if quint is None:
            print("  Quintile breakdown: skipped (fewer than 10 resolved signals)")
            monotonic = False
        else:
            print("  Quintile breakdown (0=lowest sqs, 4=highest):")
            for q, row in quint.iterrows():
                print(f"    Q{int(q)}: mean_fwd_ret={row['mean']:+.4%}  n={int(row['count'])}")
            monotonic = quint["mean"].is_monotonic_increasing
        print(f"  Monotonic (higher score -> higher forward return)?  {monotonic}")

        r1, r2 = _split_sample_check(df, h)
        stable_sign = np.sign(r1) == np.sign(r2) if not (np.isnan(r1) or np.isnan(r2)) else False
        print(f"  Split-sample Pearson: first_half={r1:+.4f}  second_half={r2:+.4f}  sign_stable={stable_sign}")

        pooled_ret = df[f"fwd_ret_{h}"].mean()
        pooled_win_rate = (df[f"fwd_ret_{h}"] > 0).mean()
        spy_ret = df[f"spy_fwd_ret_{h}"].mean()
        print(
            f"  Pooled avg BUY forward return: {pooled_ret:+.4%}  (win rate {pooled_win_rate:.1%})  "
            f"vs. avg contemporaneous SPY forward return: {spy_ret:+.4%}"
        )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--start-date",
        default="2026-08-20",
        help="Earliest signal date to include (default: the a9671ba8a formula-unification landing "
        "date - see FORMULA-REGIME NOTE in this module's docstring for why this isn't earliest-history)",
    )
    parser.add_argument("--horizons", default="5,10,20", help="Comma-separated forward-return horizons in trading days")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    horizons = [int(h) for h in args.horizons.split(",")]
    run(args.start_date, horizons)


if __name__ == "__main__":
    main()
