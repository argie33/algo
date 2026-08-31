#!/usr/bin/env python3
"""
Does the live 30%-per-field cap in _score_single_growth (loaders/load_stock_scores.py) actually
cost predictive signal versus a looser or softer cap?

Built 2026-08-31 (goal session: "most of the growth scores showing 100 seems like some issue" -
user hunch, live-confirmed via a direct DB query: 24/4859 scored symbols have growth_score EXACTLY
100.00, ~120/4859 (2.4%) are >=90, and individual GROWTH_SCORE_FIELDS columns saturate (raw value
>= the live 30% cap) for 5.4%-40.0% of their available population depending on field
(earnings_growth_4q_avg worst at 40.0%, net_income_growth_yoy 29.7%, fcf_growth_yoy 29.3%,
eps_growth_1y 28.2%) - see MAX_PLAUSIBLE_GROWTH_PCT's own docstring in
loaders/load_value_quality_growth_metrics.py confirming values up to 2000% are treated as real,
not garbage (a company crossing from near-breakeven to solidly profitable). The cap's own comment
in _score_single_growth already flags this as "domain judgment, not separately fit per field" -
this script tests that judgment empirically rather than just re-guessing a new number.

NOT a re-litigation of curve-vs-percentile-rank (already settled against percentile ranking for
growth specifically - see growth_fixed_curve_vs_relative_ranking_20260828.py's "curve clearly
better" result, reused verbatim here) or of which fields belong / sign convention (settled by
explicit user directive same as that script). Narrower question: given the SAME curve shape,
does the cap MAGNITUDE (still hard-capped at cap%) or a SOFT cap (linear to 30%, then a
compressed log tail up to 100 instead of an immediate flat ceiling) change era-robust signal.

Reuses algo/research/fama_macbeth_growth_factors.py's point-in-time panel machinery exactly like
growth_fixed_curve_vs_relative_ranking_20260828.py - same 10-of-15-field subset, same
point-in-time reporting-lag caveat, same asset_growth_yoy unflipped convention.

Usage:
    python -m algo.research.growth_cap_saturation_test_20260831 [options]
"""

import argparse
import logging
from collections.abc import Callable
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import (
    build_growth_panel,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_price_factors import fetch_month_end_prices

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

FIELDS = [
    "eps_growth_1y",
    "eps_growth_3y",
    "eps_growth_5y",
    "revenue_growth_1y",
    "revenue_growth_3y",
    "revenue_growth_5y",
    "ni_growth_yoy",
    "oi_growth_yoy",
    "fcf_growth_yoy",
    "ocf_growth_yoy",
    "asset_growth_yoy",
]
_PANEL_COLS = [f for f in FIELDS if f != "asset_growth_yoy"] + ["asset_growth_yoy_flipped"]


def _score_hard_cap(val_decimal: float, cap_pct: float) -> float:
    """Live production shape: linear [0,cap] -> [40,100], flat 100 beyond cap."""
    val = val_decimal * 100.0
    if val <= 0:
        return max(0.0, 40 + (val / 50) * 40)
    return min(100.0, 40 + (val / cap_pct) * 60)


def _score_soft_cap(val_decimal: float, linear_cap_pct: float = 30.0, ceiling_pct: float = 500.0) -> float:
    """Linear [0,linear_cap] -> [40,100] same as live, but instead of flatlining at 100 beyond
    linear_cap, keeps climbing on a compressed log scale from 100 up toward 100+log-bonus, then
    clips at ceiling_pct - preserves SOME differentiation among 30%-2000% growers instead of
    collapsing them all onto the identical score. Ceiling clip keeps a single 1999% outlier from
    dominating the equal-weighted blend the way an unbounded log would."""
    val = val_decimal * 100.0
    if val <= 0:
        return max(0.0, 40 + (val / 50) * 40)
    if val <= linear_cap_pct:
        return 40 + (val / linear_cap_pct) * 60
    excess = min(val, ceiling_pct) - linear_cap_pct
    # log1p-scaled bonus, tuned so val=ceiling_pct lands near 130 (post-rescale) - normalized
    # to 0-100 by the caller via min-max after all scores for a run are collected isn't done
    # here (keeps this a pure per-value function); instead cap the bonus itself so output stays
    # in a sane comparable band without a second global pass.
    bonus = 30.0 * np.log1p(excess / (ceiling_pct - linear_cap_pct)) / np.log1p(1.0)
    return float(100.0 + bonus)


def _percent_rank_higher_is_better(values: dict[str, float]) -> dict[str, float]:
    n = len(values)
    if n == 0:
        return dict()  # noqa: C408
    if n == 1:
        return dict.fromkeys(values, 50.0)
    sorted_items = sorted(values.items(), key=lambda kv: kv[1])
    result: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j < n and sorted_items[j][1] == sorted_items[i][1]:
            j += 1
        pct = 100.0 * i / (n - 1)
        for sym, _ in sorted_items[i:j]:
            result[sym] = pct
        i = j
    return result


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Fetching annual growth fundamentals (point-in-time reconstruction)")
    fund = fetch_annual_fundamentals()
    panel = build_growth_panel(fund)
    logger.info(f"{len(panel)} symbol-fiscal-year rows")

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly = merge_asof_monthly(months, panel, cols=_PANEL_COLS)

    variants: dict[str, Callable[[float], float]] = {
        "cap=30 (LIVE)": lambda v: _score_hard_cap(v, 30.0),
        "cap=60": lambda v: _score_hard_cap(v, 60.0),
        "cap=100": lambda v: _score_hard_cap(v, 100.0),
        "soft(30->500 log tail)": lambda v: _score_soft_cap(v, 30.0, 500.0),
    }
    records: dict[str, list[dict[str, object]]] = {name: [] for name in variants}

    for i in range(len(months) - 1):
        month = months[i]
        fund_month = monthly.get(month)
        if fund_month is None or fund_month.empty:
            continue
        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        fwd_ret = fwd_ret.replace([np.inf, -np.inf], np.nan)
        fwd_ret = fwd_ret[(fwd_ret > -0.95) & (fwd_ret < 5.0)]

        fund_month = fund_month.copy()
        fund_month["asset_growth_yoy"] = -fund_month["asset_growth_yoy_flipped"]
        cross_section = fund_month.dropna(how="all", subset=FIELDS)
        cross_section = cross_section[cross_section.index.isin(fwd_ret.index)]
        if len(cross_section) < min_cross_section:
            continue

        for symbol, row in cross_section.iterrows():
            ret = fwd_ret.get(symbol)
            if ret is None or pd.isna(ret):
                continue
            for name, fn in variants.items():
                scores = [fn(row[f]) for f in FIELDS if pd.notna(row[f])]
                if not scores:
                    continue
                records[name].append({"symbol": symbol, "month": month, "score": np.mean(scores), "fwd_ret": ret})

    dfs = {name: pd.DataFrame(recs) for name, recs in records.items()}
    for name, df in dfs.items():
        if df.empty:
            raise RuntimeError(f"No usable cross-sectional months for variant {name!r}")

    def _fm_ic(df: pd.DataFrame, label: str) -> float:
        monthly_ic = []
        for _month, g in df.groupby("month"):
            if len(g) < min_cross_section:
                continue
            ic = g["score"].corr(g["fwd_ret"], method="spearman")
            if pd.notna(ic):
                monthly_ic.append(ic)
        arr = np.array(monthly_ic)
        t_stat = arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr))) if len(arr) > 1 else float("nan")
        print(f"{label}: mean Spearman IC={arr.mean():.4f}, t={t_stat:.2f}, n_months={len(arr)}")
        return t_stat

    print("\n=== FULL SAMPLE ===")
    for name, df in dfs.items():
        _fm_ic(df, f"{name:28s} (IC)")

    all_months = sorted(dfs["cap=30 (LIVE)"]["month"].unique())
    mid = all_months[len(all_months) // 2]
    for label, lo, hi in [("FIRST HALF", all_months[0], mid), ("SECOND HALF", mid, all_months[-1])]:
        print(f"\n=== {label} ({lo} to {hi}) ===")
        for name, df in dfs.items():
            sub = df[(df["month"] >= lo) & (df["month"] <= hi)]
            _fm_ic(sub, f"{name:28s} (IC)")

    print("\n=== SATURATION CHECK (share of scores == variant's own max) ===")
    for name, df in dfs.items():
        cap = df["score"].max()
        sat_rate = (df["score"] >= cap - 1e-9).mean()
        print(f"{name:28s} max_score={cap:.2f}  share_at_or_near_max={sat_rate:.1%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    args = parser.parse_args()
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
