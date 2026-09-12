#!/usr/bin/env python3
"""Re-verify the Value x Risk pillar interaction under this session's stricter walk-forward-OOS
bar, the same standard just used for the FS/REIT/insurance-bank composite-level re-tests
(composite_score_level_industry_forward_return_genuine_panel_20260912 in memory).

Why this exists: cross_pillar_interaction_sweep_20260828.py found value_proxy x stability_proxy
(Risk) was the one pillar-pair interaction (of 15 tested) to clear this repo's own "|t|>=2 in
both halves" bar, using genuine point-in-time panels (not the circular snapshot method) - real
evidence. It was implemented as VALUE_RISK_INTERACTION_MAX_SHIFT in
loaders/stock_scores/pillar_weights.py, then RETIRED 2026-09-11 as part of a blanket
"no magnitude/t-stat-derived differential weighting anywhere" policy adopted for an unrelated
reason (composite-level weight evidence elsewhere was contaminated by imputed-vs-complete-case
disagreement) - this specific interaction's own evidence was never itself invalidated.

Session context (2026-09-12): live-verified that megacap "quality compounder" leaders (AAPL,
MSFT, V, JPM - all high risk_score/safe) rank far below where a naive user expects (composite in
the 50s-60s vs 40+/40/2300+ percentile rank out of 4812 symbols), driven by Value pillar scoring
near-zero for expensive safe names. The retired interaction is mechanistically exactly the fix:
double-sort showed Value's edge is concentrated in the riskiest tercile and ~flat for safe stocks
- yet safe megacaps still get Value at the full uniform 20% weight today.

This script settles whether that's real, decision-actionable evidence by the walk-forward-OOS
head-to-head fama_macbeth_composite_weights.py's own run() already does for ML alternatives vs
the live linear composite - reusing its exact panel-construction code (build_pillar_proxy_records,
same partial-availability sample, same expanding-window test-year split), adding ONE more
candidate to that comparison: the live composite with the Value x Risk interaction re-applied.

Usage:
    python -m algo.research.value_risk_interaction_oos_reverify_20260912
"""

import pandas as pd

from algo.research.fama_macbeth_composite_weights import (
    PILLAR_TO_LIVE_KEY,
    build_pillar_proxy_records,
    run_preflight_checks,
)
from algo.research.fama_macbeth_price_factors import print_survivorship_bias_caveat
from loaders.stock_scores.pillar_weights import BASE_PILLAR_WEIGHTS

START_DATE = "2017-06-01"
END_DATE = "2026-08-31"
MIN_CROSS_SECTION = 100

# Same magnitude the retired production code used: half of Value's base weight.
VALUE_RISK_INTERACTION_MAX_SHIFT = BASE_PILLAR_WEIGHTS["value"] * 0.5


def run() -> None:
    print_survivorship_bias_caveat()
    run_preflight_checks()
    records_partial, _records_complete, _records_raw = build_pillar_proxy_records(
        START_DATE, END_DATE, MIN_CROSS_SECTION
    )

    panel_rows = []
    for month, frame in records_partial:
        f = frame.copy()
        f["month"] = month
        panel_rows.append(f)
    panel = pd.concat(panel_rows, ignore_index=True)
    panel["year"] = pd.to_datetime(panel["month"]).dt.year
    years = sorted(panel["year"].unique())
    first_test_idx = max(1, int(len(years) * 0.6))
    test_years = years[first_test_idx:]

    live_weight_map = {c: BASE_PILLAR_WEIGHTS[k] for c, k in PILLAR_TO_LIVE_KEY.items()}

    live_pred, ix_pred, actual = [], [], []
    for test_year in test_years:
        train = panel[panel["year"] < test_year]
        test = panel[panel["year"] == test_year]
        if train.empty or len(test) < MIN_CROSS_SECTION:
            continue

        live_linear = sum(test[c] * w for c, w in live_weight_map.items())
        live_pred.extend(live_linear.tolist())

        # stability_proxy is z-scored in this panel (not 0-100 risk_score) - rescale to an
        # approximate 0-100 "higher = safer" score via the empirical CDF within this test year,
        # matching what the live risk_score percentile actually represents.
        risk_pctile = test["stability_proxy"].rank(pct=True) * 100.0
        risk_centered = ((50.0 - risk_pctile) / 50.0).clip(-1.0, 1.0)
        shift = VALUE_RISK_INTERACTION_MAX_SHIFT * risk_centered
        value_w = BASE_PILLAR_WEIGHTS["value"] + shift
        risk_w = BASE_PILLAR_WEIGHTS["risk"] - shift
        ix_score = (
            test["growth_proxy"] * BASE_PILLAR_WEIGHTS["growth"]
            + test["value_proxy"] * value_w
            + test["quality_proxy"] * BASE_PILLAR_WEIGHTS["quality"]
            + test["stability_proxy"] * risk_w
            + test["momentum_proxy"] * BASE_PILLAR_WEIGHTS["momentum"]
        )
        ix_pred.extend(ix_score.tolist())

        actual.extend(test["fwd_ret"].tolist())

    if not live_pred:
        print("No usable walk-forward test years - check MIN_CROSS_SECTION.")
        return

    live_s = pd.Series(live_pred)
    ix_s = pd.Series(ix_pred)
    act_s = pd.Series(actual)

    print(f"OOS symbol-months: {len(live_pred)}, test years: {test_years}\n")
    print(f"{'method':40s} {'Spearman':>10s} {'Pearson':>10s}")
    print(
        f"{'live_linear (uniform 20% each)':40s} {live_s.corr(act_s, method='spearman'):10.4f} {live_s.corr(act_s, method='pearson'):10.4f}"
    )
    print(
        f"{'value_x_risk_interaction (restored)':40s} {ix_s.corr(act_s, method='spearman'):10.4f} {ix_s.corr(act_s, method='pearson'):10.4f}"
    )

    delta_spearman = ix_s.corr(act_s, method="spearman") - live_s.corr(act_s, method="spearman")
    print(f"\nDelta Spearman IC (interaction - live_linear): {delta_spearman:+.4f}")
    print(
        "\nVerdict rule: interaction should only be restored to production if delta is positive"
        " AND the effect isn't a single-year fluke - inspect the per-year breakdown below."
    )

    print(f"\n{'test_year':>10s} {'live_linear':>12s} {'interaction':>12s} {'n':>6s}")
    idx = 0
    for test_year in test_years:
        test = panel[panel["year"] == test_year]
        if len(test) < MIN_CROSS_SECTION:
            continue
        n = len(test)
        yr_live = live_s.iloc[idx : idx + n]
        yr_ix = ix_s.iloc[idx : idx + n]
        yr_act = act_s.iloc[idx : idx + n]
        print(
            f"{test_year:>10d} {yr_live.corr(yr_act, method='spearman'):12.4f}"
            f" {yr_ix.corr(yr_act, method='spearman'):12.4f} {n:6d}"
        )
        idx += n


if __name__ == "__main__":
    run()
