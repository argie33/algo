#!/usr/bin/env python3
"""Tests 2 genuinely new (never-evaluated) composite-input candidates surfaced by a full
168-table DB survey this session, per user directive to check whether the composite needs
data sources beyond what the 5 existing pillars already use:

- analyst_upgrade_downgrade (152,228 rows, real depth 2024-07-29 to 2026-10-05, ~2.3 years -
  thinner than this project's usual ~110-month standard, disclosed not hidden): net analyst
  rating-revision signal (Womack 1996; Jegadeesh/Kim/Krische/Lee 2004).
- dividend_data (148,608 rows, real depth 2005-05-15 to 2026-09-16, 21 years): dividend growth
  rate and a cut/no-cut flag - the live Value pillar only scores a single trailing
  dividend_yield (11%), never dividend GROWTH or a cut signal (Michaely/Thaler/Womack 1995;
  Benartzi/Michaely/Thaler 1997 - dividend cuts predict poor forward returns).

A third candidate (Standardized Unexpected Earnings via quarterly_income_statement) was
investigated and DROPPED before building anything: quarterly_income_statement.earnings_per_share
is corrupted (cumulative/YTD within-fiscal-year, not discrete quarterly) for essentially every
row loaded before the 2026-08-29 discrete-vs-cumulative fix (commit 9926a2d90,
utils/external/sec_statements.py) - live-verified AAPL 2018 rows (updated_at 2026-08-18, still
cumulative: Q1=4.22/Q2=6.69/Q3=9.07) and META 2026 rows (updated_at 2026-08-26, same pattern:
Q1=10.57/Q2=16.79). Only rows reloaded ON/AFTER 2026-08-29 are correct (AAPL 2026 Q2/Q3,
updated_at 2026-08-29, correctly flat: 2.02/2.03). No backfill has run - this is a genuine,
still-live production data-quality gap (not scoped to fix here), and it likely also affects the
live-scored GROWTH_SCORE_FIELDS quarterly_growth_momentum/earnings_growth_4q_avg for any symbol
not reloaded since 2026-08-29, not just this SUE candidate - flagged for the parent session, out
of this script's scope to fix.

Methodology: reuses fama_macbeth_composite_weights.py's build_pillar_proxy_records() for the
5-pillar-proxy panel (growth/value/quality/stability/momentum + fwd_ret) as both the merge
target and the multivariate control set. Same Fama-MacBeth monthly cross-sectional regression +
first/second-half robustness bar (|t|>=2 AND same sign both halves) as every other factor test
in this project.
"""

import argparse
import logging
from datetime import date

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import PILLAR_COLS, build_pillar_proxy_records
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def _zwinsor(s: pd.Series) -> pd.Series:
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def fetch_analyst_actions() -> pd.DataFrame:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT symbol, action_date, action
            FROM analyst_upgrade_downgrade
            WHERE action_date IS NOT NULL AND action IN ('up', 'down')
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "action_date", "action"])
    df["action_date"] = pd.to_datetime(df["action_date"])
    return df


def analyst_net_signal_for_month(actions: pd.DataFrame, month_end: pd.Timestamp, window_days: int = 90) -> pd.Series:
    """Net (up-down)/(up+down) rating-revision signal per symbol in the trailing window_days
    ending at month_end - point-in-time by construction (action_date is a real historical
    event date, no lookahead)."""
    start = month_end - pd.Timedelta(days=window_days)
    win = actions[(actions["action_date"] > start) & (actions["action_date"] <= month_end)]
    if win.empty:
        return pd.Series(dtype=float)
    g = win.groupby(["symbol", "action"]).size().unstack(fill_value=0)
    for col in ("up", "down"):
        if col not in g.columns:
            g[col] = 0
    total = g["up"] + g["down"]
    return ((g["up"] - g["down"]) / total).where(total > 0)


def fetch_dividends() -> pd.DataFrame:
    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT symbol, ex_dividend_date, dividend_per_share
            FROM dividend_data
            WHERE ex_dividend_date IS NOT NULL AND dividend_per_share IS NOT NULL
              AND dividend_type IS DISTINCT FROM 'special'
        """)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "ex_dividend_date", "dps"])
    df["ex_dividend_date"] = pd.to_datetime(df["ex_dividend_date"])
    df["dps"] = df["dps"].astype(float)
    return df.sort_values(["symbol", "ex_dividend_date"])


def dividend_growth_and_cut_for_month(div: pd.DataFrame, month_end: pd.Timestamp) -> pd.DataFrame:
    """TTM dividend-per-share sum as of month_end vs. the prior TTM window, per symbol -
    point-in-time (only uses ex_dividend_date <= month_end). growth = ttm_now/ttm_prior - 1;
    cut_flag = 1 if growth <= -0.10 (a real >=10% TTM dividend cut), else 0. NaN when there's no
    real prior-TTM dividend history to compare against (never fabricate a "no cut" for a symbol
    that simply doesn't pay dividends or has <2yr of payment history)."""
    cur_start = month_end - pd.Timedelta(days=365)
    prior_start = month_end - pd.Timedelta(days=730)
    cur_win = div[(div["ex_dividend_date"] > cur_start) & (div["ex_dividend_date"] <= month_end)]
    prior_win = div[(div["ex_dividend_date"] > prior_start) & (div["ex_dividend_date"] <= cur_start)]
    ttm_now = cur_win.groupby("symbol")["dps"].sum()
    ttm_prior = prior_win.groupby("symbol")["dps"].sum()
    both = pd.DataFrame({"ttm_now": ttm_now, "ttm_prior": ttm_prior}).dropna()
    both = both[both["ttm_prior"] > 0]
    if both.empty:
        return pd.DataFrame(columns=["div_growth", "div_cut_flag"])
    growth = both["ttm_now"] / both["ttm_prior"] - 1.0
    cut_flag = (growth <= -0.10).astype(float)
    return pd.DataFrame({"div_growth": growth, "div_cut_flag": cut_flag})


def _fm_test(
    panel: pd.DataFrame, candidate_col: str, controls: list[str] | None, months: pd.DatetimeIndex
) -> dict[str, float]:
    """Fama-MacBeth: per-month OLS of fwd_ret on candidate_col (+ controls if given, all
    z-scored per month already), average coefficient / se(coef)/sqrt(n_months) = t-stat.
    Splits months into first/second half by count, same convention as every other script here.
    Uses sklearn.linear_model.LinearRegression (statsmodels isn't installed in this
    environment) - candidate_col's coefficient index is tracked explicitly via the fitted
    column order, not a named-params lookup."""
    from sklearn.linear_model import LinearRegression

    coefs = []
    cols = [candidate_col] + (controls or [])
    candidate_idx = 0  # candidate_col is always first in `cols`
    month_list = sorted(panel["month"].unique())
    for m in month_list:
        sub = panel[panel["month"] == m]
        sub = sub.dropna(subset=[*cols, "fwd_ret"])
        if len(sub) < 30:
            continue
        x = sub[cols].to_numpy()
        y = sub["fwd_ret"].to_numpy()
        try:
            reg = LinearRegression().fit(x, y)
            coefs.append((m, float(reg.coef_[candidate_idx])))
        except Exception:
            continue
    if len(coefs) < 6:
        return {"n_months": len(coefs), "t_full": float("nan"), "t_era1": float("nan"), "t_era2": float("nan")}
    s = pd.Series(dict(coefs)).sort_index()
    n = len(s)
    half = n // 2

    def _t(x: pd.Series) -> float:
        if len(x) < 3 or x.std() == 0:
            return float("nan")
        return float(x.mean() / (x.std() / np.sqrt(len(x))))

    return {
        "n_months": n,
        "mean_coef": float(s.mean()),
        "t_full": _t(s),
        "t_era1": _t(s.iloc[:half]),
        "t_era2": _t(s.iloc[half:]),
    }


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Building 5-pillar-proxy panel (reused for merge target + multivariate control)")
    _records_partial, _records_complete, records_raw = build_pillar_proxy_records(
        start_date, end_date, min_cross_section
    )
    logger.info(f"records_raw: {len(records_raw)} months")

    logger.info("Fetching analyst_upgrade_downgrade actions")
    actions = fetch_analyst_actions()
    logger.info(f"{len(actions)} up/down actions, {actions['action_date'].min()} to {actions['action_date'].max()}")

    logger.info("Fetching dividend_data")
    div = fetch_dividends()
    logger.info(f"{len(div)} dividend rows, {div['ex_dividend_date'].min()} to {div['ex_dividend_date'].max()}")

    rows_a = []
    rows_b = []
    for month, raw in records_raw:
        month_end = pd.Timestamp(month) + pd.offsets.MonthEnd(0)

        analyst_sig = analyst_net_signal_for_month(actions, month_end)
        if not analyst_sig.empty:
            merged = raw.join(analyst_sig.rename("analyst_net"), how="inner")
            merged = merged.dropna(subset=["analyst_net", "fwd_ret"])
            if len(merged) >= 30:
                merged = merged.copy()
                merged["analyst_net"] = _zwinsor(merged["analyst_net"])
                for c in PILLAR_COLS:
                    merged[c] = _zwinsor(merged[c])
                merged["month"] = month
                rows_a.append(merged)

        div_sig = dividend_growth_and_cut_for_month(div, month_end)
        if not div_sig.empty:
            merged = raw.join(div_sig, how="inner")
            merged = merged.dropna(subset=["fwd_ret"])
            if len(merged) >= 30:
                merged = merged.copy()
                merged["div_growth_z"] = _zwinsor(merged["div_growth"])
                for c in PILLAR_COLS:
                    merged[c] = _zwinsor(merged[c])
                merged["month"] = month
                rows_b.append(merged)

    panel_a = pd.concat(rows_a, ignore_index=False) if rows_a else pd.DataFrame()
    panel_b = pd.concat(rows_b, ignore_index=False) if rows_b else pd.DataFrame()

    months_a = sorted(panel_a["month"].unique()) if not panel_a.empty else []
    months_b = sorted(panel_b["month"].unique()) if not panel_b.empty else []

    print("\n=== CANDIDATE A: analyst_upgrade_downgrade net rating-revision signal (90d window) ===")
    print(
        f"Months with usable overlap: {len(months_a)} ({months_a[0] if months_a else '-'} to {months_a[-1] if months_a else '-'})"
    )
    print(f"Total symbol-months: {len(panel_a)}")
    if not panel_a.empty:
        uni = _fm_test(panel_a, "analyst_net", None, pd.DatetimeIndex(months_a))
        multi = _fm_test(panel_a, "analyst_net", PILLAR_COLS, pd.DatetimeIndex(months_a))
        print(
            f"Univariate:   n_months={uni['n_months']} t_full={uni['t_full']:.2f} t_era1={uni['t_era1']:.2f} t_era2={uni['t_era2']:.2f}"
        )
        print(
            f"Multivariate: n_months={multi['n_months']} t_full={multi['t_full']:.2f} t_era1={multi['t_era1']:.2f} t_era2={multi['t_era2']:.2f}"
        )
        robust_uni = (
            abs(uni["t_full"]) >= 2
            and abs(uni["t_era1"]) >= 2
            and abs(uni["t_era2"]) >= 2
            and (uni["t_era1"] > 0) == (uni["t_era2"] > 0)
        )
        robust_multi = (
            abs(multi["t_full"]) >= 2
            and abs(multi["t_era1"]) >= 2
            and abs(multi["t_era2"]) >= 2
            and (multi["t_era1"] > 0) == (multi["t_era2"] > 0)
        )
        print(f"Robust (|t|>=2 AND same sign both halves)? univariate={robust_uni} multivariate={robust_multi}")
        print(
            "CAVEAT: only ~2.3yr of real analyst_upgrade_downgrade history exists - half-split here is ~13-14 months per half, far thinner than this project's usual ~55-month half-splits. Treat as preliminary, not equal-strength evidence."
        )
    else:
        print("No usable overlap months - candidate not testable with current data.")

    print("\n=== CANDIDATE B: dividend_data TTM growth rate ===")
    print(
        f"Months with usable overlap: {len(months_b)} ({months_b[0] if months_b else '-'} to {months_b[-1] if months_b else '-'})"
    )
    print(f"Total symbol-months: {len(panel_b)}")
    if not panel_b.empty:
        uni = _fm_test(panel_b, "div_growth_z", None, pd.DatetimeIndex(months_b))
        multi = _fm_test(panel_b, "div_growth_z", PILLAR_COLS, pd.DatetimeIndex(months_b))
        print(
            f"Univariate:   n_months={uni['n_months']} t_full={uni['t_full']:.2f} t_era1={uni['t_era1']:.2f} t_era2={uni['t_era2']:.2f}"
        )
        print(
            f"Multivariate: n_months={multi['n_months']} t_full={multi['t_full']:.2f} t_era1={multi['t_era1']:.2f} t_era2={multi['t_era2']:.2f}"
        )
        robust_uni = (
            abs(uni["t_full"]) >= 2
            and abs(uni["t_era1"]) >= 2
            and abs(uni["t_era2"]) >= 2
            and (uni["t_era1"] > 0) == (uni["t_era2"] > 0)
        )
        robust_multi = (
            abs(multi["t_full"]) >= 2
            and abs(multi["t_era1"]) >= 2
            and abs(multi["t_era2"]) >= 2
            and (multi["t_era1"] > 0) == (multi["t_era2"] > 0)
        )
        print(f"Robust (|t|>=2 AND same sign both halves)? univariate={robust_uni} multivariate={robust_multi}")

        print("\n--- Dividend CUT FLAG (binary, TTM decline >=10%) as its own univariate test ---")
        cut_rows = []
        for month, raw in records_raw:
            month_end = pd.Timestamp(month) + pd.offsets.MonthEnd(0)
            div_sig = dividend_growth_and_cut_for_month(div, month_end)
            if div_sig.empty:
                continue
            merged = raw.join(div_sig[["div_cut_flag"]], how="inner").dropna(subset=["fwd_ret"])
            if len(merged) >= 30:
                merged = merged.copy()
                merged["month"] = month
                cut_rows.append(merged)
        if cut_rows:
            panel_cut = pd.concat(cut_rows, ignore_index=False)
            uni_cut = _fm_test(panel_cut, "div_cut_flag", None, pd.DatetimeIndex(sorted(panel_cut["month"].unique())))
            print(
                f"Cut flag univariate: n_months={uni_cut['n_months']} t_full={uni_cut['t_full']:.2f} t_era1={uni_cut['t_era1']:.2f} t_era2={uni_cut['t_era2']:.2f} mean_coef={uni_cut.get('mean_coef', float('nan')):.5f}"
            )
            n_cuts = int(panel_cut["div_cut_flag"].sum())
            print(f"Total symbol-months flagged as a cut: {n_cuts} / {len(panel_cut)}")
    else:
        print("No usable overlap months - candidate not testable with current data.")

    print("\n=== SANITY CHECKS ===")
    if not panel_a.empty:
        print(
            f"analyst_net range: [{panel_a['analyst_net'].min():.3f}, {panel_a['analyst_net'].max():.3f}] (pre-zscore would be [-1,1])"
        )
    if not panel_b.empty:
        print(
            f"div_growth (raw, pre-zscore) 1st/50th/99th pct: {panel_b['div_growth'].quantile([0.01, 0.5, 0.99]).values}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=300)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
