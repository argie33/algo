#!/usr/bin/env python3
"""
Tests compensatory blending (current composite_score architecture) against a gate-then-rank
hybrid (require convergence across pillars before ranking) - built 2026-09-15 (/goal session,
direct follow-up to a live-verified fact: IBD's own published guidance is "require BOTH EPS and
RS to be above a defined threshold (e.g., 80+) before moving to deeper research," i.e. a GATE on
individual ratings, not reliance on the blended Composite Rating number alone). Confirmed against
the academic literature too: compensatory (additive/weighted-sum) scoring structurally lets a
strong score on one factor mask weak scores on others; non-compensatory (conjunctive/gating)
approaches specifically favor "all-rounder" convergence over one standout dimension. These are
genuinely different selection mechanisms, not just a weight-tuning question - worth testing
before finalizing any composite weight decision, since fixing weights on the wrong architecture
wouldn't have caught this.

WHY TOP-DECILE REALIZED RETURN, NOT POOLED SPEARMAN IC: every other script in this family
measures cross-sectional Spearman IC across the WHOLE universe each month, which weighs every
rank position equally. That's the right question for "does this pillar/weight scheme predict
returns at all," but it's the wrong question for "which stocks would we actually end up buying"
- the thing this whole /goal session is trying to get right ("the best stock opportunity"). This
script instead forms the actual top-decile portfolio each month under each construction and
reports its REALIZED forward return - the number a portfolio manager would actually experience,
not an average correlation across the full ranked universe including stocks nobody would trade.

TWO CONSTRUCTIONS COMPARED, same underlying raw pillar data (build_pillar_proxy_records,
percentile-ranked per IBD's own disclosed 1-99 scale convention - see
composite_ibd_style_construction.py for why percentile over z-score is being tested this
session):
  A) COMPENSATORY BLEND (current architecture): top decile by equal-weighted composite score,
     no individual-pillar floor - a stock with extreme Momentum and weak Quality can still make
     the top decile if the blended average is high enough.
  B) GATE-THEN-RANK: eligibility requires growth_proxy percentile >= GATE_PCTL AND
     momentum_proxy percentile >= GATE_PCTL (the two pillars IBD's own disclosed EPS+RS gate
     example uses) - THEN rank by the same equal-weighted composite score among only the
     eligible survivors, take the top decile of THAT eligible pool.

Both portfolios are equal-weighted, monthly-rebalanced, no transaction costs modeled (same
simplification as every other script in this family - a genuine limitation, not hidden).

Usage:
    python -m algo.research.composite_gate_vs_blend_topdecile [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import PILLAR_COLS, build_pillar_proxy_records
from algo.research.fama_macbeth_price_factors import print_survivorship_bias_caveat
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

GATE_PCTL = 50.0  # median - matches "above average," a moderate reading of IBD's disclosed 80+ example scaled to our smaller universe
TOP_DECILE_PCTL = 90.0

LIVE_WEIGHTS = {
    "growth_proxy": BASE_PILLAR_WEIGHTS["growth"],
    "value_proxy": BASE_PILLAR_WEIGHTS["value"],
    "quality_proxy": BASE_PILLAR_WEIGHTS["quality"],
    "stability_proxy": BASE_PILLAR_WEIGHTS["risk"],
    "momentum_proxy": BASE_PILLAR_WEIGHTS["momentum"],
}


def _percentile_rank(s: pd.Series) -> pd.Series:
    return s.rank(pct=True) * 100.0


def _month_top_decile_returns(frame: pd.DataFrame, gated: bool) -> float | None:
    pct = frame.copy()
    for col in PILLAR_COLS:
        pct[col] = _percentile_rank(frame[col])

    if gated:
        eligible = pct[(pct["growth_proxy"] >= GATE_PCTL) & (pct["momentum_proxy"] >= GATE_PCTL)]
    else:
        eligible = pct

    if len(eligible) < 20:
        return None

    composite = sum(eligible[c].values * w for c, w in LIVE_WEIGHTS.items())
    threshold = np.percentile(composite, TOP_DECILE_PCTL)
    top = eligible.loc[composite >= threshold]
    if len(top) == 0:
        return None
    return float(top["fwd_ret"].mean())


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    print_survivorship_bias_caveat()
    _records_partial, records_complete, _records_raw = build_pillar_proxy_records(
        start_date, end_date, min_cross_section
    )
    if not records_complete:
        raise RuntimeError("No complete-case months available")

    holdout = [(m, f) for m, f in records_complete if m.year >= 2022]
    holdout_years = sorted({m.year for m, _f in holdout})

    rows = []
    for month, frame in holdout:
        blend_ret = _month_top_decile_returns(frame, gated=False)
        gate_ret = _month_top_decile_returns(frame, gated=True)
        rows.append({"month": month, "year": month.year, "blend": blend_ret, "gated": gate_ret})

    df = pd.DataFrame(rows).dropna()

    print(f"\nHoldout years: {holdout_years}, usable months: {len(df)}")
    print(
        f"Gate: growth_proxy & momentum_proxy both >= {GATE_PCTL:.0f}th percentile (IBD's own disclosed EPS+RS gate example)"
    )
    print(
        f"Portfolio: top {100 - TOP_DECILE_PCTL:.0f}% by equal-weighted composite score, equal-weighted, monthly rebalance, no costs modeled\n"
    )

    print(
        f"{'year':6s} {'n_months':>9s} {'blend_mean_ret':>15s} {'gated_mean_ret':>15s} {'blend_sharpe*':>14s} {'gated_sharpe*':>14s}"
    )
    for year in holdout_years:
        yd = df[df["year"] == year]
        if yd.empty:
            continue
        b_mean, g_mean = yd["blend"].mean(), yd["gated"].mean()
        b_sharpe = b_mean / yd["blend"].std(ddof=1) if yd["blend"].std(ddof=1) > 0 else float("nan")
        g_sharpe = g_mean / yd["gated"].std(ddof=1) if yd["gated"].std(ddof=1) > 0 else float("nan")
        print(f"{year:<6d} {len(yd):>9d} {b_mean:15.4%} {g_mean:15.4%} {b_sharpe:14.3f} {g_sharpe:14.3f}")

    print(
        f"\n{'OVERALL':6s} {len(df):>9d} {df['blend'].mean():15.4%} {df['gated'].mean():15.4%} "
        f"{(df['blend'].mean() / df['blend'].std(ddof=1)):14.3f} {(df['gated'].mean() / df['gated'].std(ddof=1)):14.3f}"
    )
    print(
        "(*monthly Sharpe-like ratio: mean/std of monthly top-decile returns within each year - not annualized, comparison only)"
    )

    n_gate_wins = int((df["gated"] > df["blend"]).sum())
    print(f"\nGated portfolio beat blend portfolio in {n_gate_wins}/{len(df)} months ({n_gate_wins / len(df):.1%})")
    print(
        "\nInterpretation: this is a REALIZED top-decile portfolio comparison, not a pooled IC - "
        "it directly answers whether requiring growth+momentum convergence before ranking "
        "produces better actual picks than blending alone. A real win needs BOTH higher mean "
        "return AND comparable-or-better Sharpe, consistently across years - not just one good "
        "year driving the average, same era-robustness standard as every other test this session."
    )
    print("\nNo production scoring logic was changed by this script.")


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
