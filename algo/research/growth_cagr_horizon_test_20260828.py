#!/usr/bin/env python3
"""
Tests whether revenue/eps 3Y and 5Y CAGR carry independent predictive signal beyond the
live 5-input equal-weighted Growth blend, and whether adding them improves it.

Built 2026-08-28 (goal: user pushback - "industry best practice looks across periods", and
a direct challenge to this pillar's own inherited claim that 3Y/5Y CAGR are "time-window
duplicates" of the 1Y versions). That claim was never actually backed by a correlation number
specific to 1Y-vs-3Y/5Y in this repo's docstrings - checked directly against growth_metrics
(4,917 rows): Spearman rank correlation is only 0.49-0.70 between 1Y and 3Y/5Y CAGR pairs, NOT
duplicate-level (>0.85+) - a real, quantified correction to that assumption.

Separately confirmed via web search: MSCI's actual Growth Index methodology uses 5 variables -
long-term forward EPS growth, short-term forward EPS growth, current internal growth rate (=
ROE x retention ratio, i.e. exactly this pillar's sustainable_growth_rate), long-term
historical EPS growth TREND, and long-term historical sales-per-share growth TREND (both
computed via 5-year OLS regression, not a simple 2-point CAGR like this repo's revenue_growth_
3y/5y). IBD CAN SLIM explicitly uses BOTH current-quarter YoY (recency) AND 3-year annual
growth (trend) together, not as substitutes - "looking across periods" is real industry
practice, not this session's earlier over-quick dismissal.

This script tests the CAGR fields the way this repo actually has them (2-point endpoint CAGR,
not a regression trend - a real methodology gap flagged but not fixed here, out of scope for
today) via algo/research/fama_macbeth_growth_factors.py's existing revenue_growth_3y/5y,
eps_growth_3y/5y (already computed there, never previously isolated-FM-tested for THIS
specific redundancy claim).

Usage:
    python -m algo.research.growth_cagr_horizon_test_20260828
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import _zwinsor
from algo.research.fama_macbeth_growth_factors import (
    build_growth_panel,
    fetch_annual_fundamentals,
)
from algo.research.fama_macbeth_growth_factors import (
    merge_asof_monthly as merge_asof_monthly_growth,
)
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.growth_reinvestment_book_value_candidates import build_panel as build_book_value_panel
from algo.research.growth_reinvestment_book_value_candidates import fetch_panel_raw as fetch_book_value_fundamentals

logger = logging.getLogger(__name__)

LIVE_5 = ["revenue_growth_1y", "eps_growth_1y", "ocf_growth_yoy", "book_value_growth", "sustainable_growth_rate"]
CAGR_CANDIDATES = ["revenue_growth_3y", "revenue_growth_5y", "eps_growth_3y", "eps_growth_5y"]


def _renormalized_blend(z: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    w = pd.Series(weights)
    avail = z.notna()
    w_matrix = avail.mul(w, axis=1)
    row_weight_sum = w_matrix.sum(axis=1)
    weighted = (z.fillna(0.0) * w_matrix).sum(axis=1)
    out = pd.Series(np.nan, index=z.index)
    valid = row_weight_sum > 0
    out.loc[valid] = weighted.loc[valid] / row_weight_sum.loc[valid]
    return out


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Building fundamentals panels")
    growth_raw = fetch_annual_fundamentals()
    growth_panel = build_growth_panel(growth_raw)
    bv_panel = build_book_value_panel(fetch_book_value_fundamentals())
    quality_raw = fetch_annual_quality_fundamentals()
    quality_fund = build_quality_panel(quality_raw)
    quality_fund["sustainable_growth_rate"] = np.where(
        quality_fund["payout_ratio"].notna(),
        quality_fund["roe"] * (1.0 - quality_fund["payout_ratio"].clip(0.0, 1.0)),
        np.nan,
    )

    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    growth_monthly = merge_asof_monthly_growth(
        months, growth_panel, cols=["revenue_growth_1y", "eps_growth_1y", "ocf_growth_yoy", *CAGR_CANDIDATES]
    )
    bv_monthly = merge_asof_monthly_growth(months, bv_panel, cols=["book_value_growth"])
    quality_monthly = merge_asof_monthly_growth(months, quality_fund, cols=["sustainable_growth_rate"])

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - 1):
        month = months[i]
        gr = growth_monthly.get(month)
        bv = bv_monthly.get(month)
        q = quality_monthly.get(month)
        if gr is None or bv is None or q is None or gr.empty or bv.empty or q.empty:
            continue

        idx = gr.index.union(bv.index).union(q.index)
        cand = pd.DataFrame(index=idx)
        for col in LIVE_5:
            if col == "book_value_growth":
                cand[col] = bv["book_value_growth"].reindex(idx)
            elif col == "sustainable_growth_rate":
                cand[col] = q["sustainable_growth_rate"].reindex(idx)
            else:
                cand[col] = gr[col].reindex(idx)
        for col in CAGR_CANDIDATES:
            cand[col] = gr[col].reindex(idx)

        z = pd.DataFrame(index=idx)
        for col in [*LIVE_5, *CAGR_CANDIDATES]:
            z[col] = -_zwinsor(cand[col])  # sign-flip convention, matches live _score_growth

        growth_live5 = _renormalized_blend(z[LIVE_5], dict.fromkeys(LIVE_5, 1.0))
        growth_plus_cagr = _renormalized_blend(
            z[[*LIVE_5, *CAGR_CANDIDATES]], dict.fromkeys([*LIVE_5, *CAGR_CANDIDATES], 1.0)
        )

        fwd_ret = px.iloc[i + 1].reindex(idx) / px.iloc[i].reindex(idx) - 1.0

        frame = pd.DataFrame({"growth_live5": growth_live5, "growth_plus_cagr": growth_plus_cagr, "fwd_ret": fwd_ret})
        for col in CAGR_CANDIDATES:
            frame[col] = z[col]
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})\n")

    split_idx = len(records) // 2
    halves = {"FULL": records, "ERA1": records[:split_idx], "ERA2": records[split_idx:]}

    print("########## Isolated univariate Fama-MacBeth: each CAGR candidate alone ##########\n")
    print(f"{'candidate':20s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for cand in CAGR_CANDIDATES:
        for era_label, era_records in halves.items():
            usable = [(m, f.dropna(subset=[cand, "fwd_ret"])) for m, f in era_records]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if not usable:
                continue
            mean, t = _fama_macbeth(usable, [cand])[cand]
            print(f"{cand:20s} {era_label:6s} {mean:10.5f} {t:8.2f} {len(usable):9d}")
        print()

    print("########## LIVE 5-input blend vs LIVE-5 + 4 CAGR fields (9-input) blend ##########\n")
    print(f"{'variant':20s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in ["growth_live5", "growth_plus_cagr"]:
        for era_label, era_records in halves.items():
            usable = [(m, f.dropna(subset=[variant, "fwd_ret"])) for m, f in era_records]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section and f[variant].std() > 0]
            if not usable:
                continue
            mean, t = _fama_macbeth(usable, [variant])[variant]
            print(f"{variant:20s} {era_label:6s} {mean:10.5f} {t:8.2f} {len(usable):9d}")
        print()

    print("########## Coverage ##########\n")
    for cand in [*CAGR_CANDIDATES, "growth_live5", "growth_plus_cagr"]:
        cov = np.mean([f[cand].notna().mean() for _, f in records])
        print(f"  {cand:20s} {cov * 100:6.1f}%")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2015-06-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
