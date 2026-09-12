#!/usr/bin/env python3
"""
Confirmatory test of 3 composite-reweighting candidates against the live equal-weight
BASE_PILLAR_WEIGHTS, per the WEIGHT-REVISION GOVERNANCE POLICY in
loaders/stock_scores/pillar_weights.py (a candidate must clear FDR-corrected significance,
same-era-sign robustness, AND avoid the circular snapshot-vs-trailing-return trap before being
trusted for a production weight decision).

Built 2026-09-12, direct follow-up to a same-day exploratory run of
algo/research/fama_macbeth_composite_weights.py that found (a) none of the 5 pillars
individually clear |t|>=2 in even one era-half, and (b) ONE walk-forward OOS run where a
Lasso(alpha=1e-3) got Spearman IC 0.081 vs live equal-weight's 0.076 by zeroing out Growth and
Quality. That was a single point-estimate comparison, not a significance test - exactly the
"one exploratory run is not confirmation" gap this script exists to close, using the SAME
non-circular point-in-time panel machinery (build_pillar_proxy_records), not a new one.

THREE CANDIDATES TESTED, none of them fit/tuned on this panel (so there is no train/test
leakage question for any of them - all three are FIXED rules, exactly like the live formula):

  1. DROP_GQ: equal-weight Value+Risk+Momentum only (1/3 each), Growth and Quality zeroed -
     directly implements what the Lasso run found, as a fixed rule rather than a fitted model.
  2. GARP_CAP: live equal-weight formula unchanged, EXCEPT value_proxy is floored at that
     month's cross-sectional median (z=0) for any row where Quality, Risk, AND Momentum are
     ALL in that month's top tercile (>= its 67th percentiles) - implements "don't let Value
     veto a name whose other three pillars are all elite" without zero-weighting Value
     everywhere. Threshold (top tercile, all 3) and floor (median, not full zero-out) were
     chosen to be a moderate, reasoned guardrail rather than fit to the data - this repo's own
     standing practice (see pillar_weights.py's retired VALUE_RISK_INTERACTION_MAX_SHIFT note)
     is "a real, evidenced direction conservatively, not the literal point estimate."
  3. COMBINED: DROP_GQ's pillar set (Value+Risk+Momentum, 1/3 each) with GARP_CAP's value floor
     applied on top (gate computed from Risk/Momentum plus quality_proxy even though quality
     is not in the weighted sum, since the gate is a screen, not a scoring input).

METHODOLOGY: reuses build_pillar_proxy_records()'s already-validated PIT panel (real annual
fundamentals with reporting-lag-aware known_date, real monthly price panel, genuine forward
1-month return - no snapshot tables, no circularity). Restricts to the SAME walk-forward OOS
test-year window fama_macbeth_composite_weights.py uses (last ~40% of years by calendar year),
so results are directly comparable to that script's reported IC 0.076 baseline. Computes
Spearman IC PER MONTH (not just pooled) for live equal-weight and each candidate, then runs:
  - A paired Wilcoxon signed-rank test on the per-month IC differences (candidate - live) -
    the right test for "is this candidate's edge real or one lucky pooled sample," since it
    respects the paired, non-independent structure (same months, same underlying market draws).
  - A paired bootstrap (5,000 resamples of the month index) as a second, distribution-free
    cross-check of the same question.
  - A first-half/second-half split of the OOS window, requiring the SAME SIGN in both halves
    before "the candidate wins" is treated as anything more than a pooled-sample artifact -
    this file's own standing bar (see fama_macbeth_composite_weights.py's AGREEMENT CHECK
    section) applied to candidate-vs-baseline comparisons, not just raw pillar coefficients.
  - Benjamini-Hochberg FDR correction (q=0.10) across the 3-candidate family, per the standing
    governance policy - a bare |t|>=2 / p<0.05 read on any ONE of these would not clear the bar
    on its own with 3 candidates screened in the same pass.

SEPARATELY, illustrative-only (NOT a significance test): recomputes where AAPL/MSFT/JPM/V/
BRK.B/GOOGL/META/AMZN/WMT actually rank TODAY in the live stock_scores table under each
candidate's formula, to show concretely whether a candidate that clears the statistical bar
also does anything to the mega-cap-suppression symptom that motivated this whole test, or
whether the two questions are more separate than they look.

This script makes NO production changes. It is read-only against `algo/research/
fama_macbeth_composite_weights.py`'s panel builder and the live `stock_scores`/`company_profile`
tables (SELECT only).

Usage:
    python -m algo.research.composite_reweighting_candidates_20260912 [--start-date ...]
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from algo.research.fama_macbeth_composite_weights import (
    PILLAR_COLS,
    PILLAR_TO_LIVE_KEY,
    build_pillar_proxy_records,
)
from algo.research.fama_macbeth_price_factors import benjamini_hochberg_fdr, print_survivorship_bias_caveat
from loaders.load_stock_scores import BASE_PILLAR_WEIGHTS
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

MEGACAP_SYMBOLS = ["AAPL", "MSFT", "JPM", "V", "BRK.B", "GOOGL", "META", "AMZN", "WMT"]

# GARP gate: all three of Quality/Risk/Momentum must be in the top tercile (moderate, not an
# extreme top-decile screen) for Value's floor to kick in - see module docstring.
GARP_GATE_PERCENTILE = 2.0 / 3.0


def _monthly_ic(panel: pd.DataFrame, pred_col: str) -> pd.Series:
    """Per-month Spearman IC between `pred_col` and fwd_ret, indexed by month."""
    out = {}
    for month, g in panel.groupby("month"):
        if g[pred_col].nunique() < 5:
            continue
        out[month] = g[pred_col].corr(g["fwd_ret"], method="spearman")
    return pd.Series(out).dropna()


def _paired_test(live_ic: pd.Series, cand_ic: pd.Series, label: str) -> dict[str, float]:
    common = live_ic.index.intersection(cand_ic.index)
    diff = (cand_ic.loc[common] - live_ic.loc[common]).values
    n = len(diff)

    wilcoxon_p = float("nan")
    if n >= 6 and np.any(diff != 0):
        _stat, wilcoxon_p = scipy_stats.wilcoxon(diff)

    rng = np.random.default_rng(20260912)
    boot_means = np.array([rng.choice(diff, size=n, replace=True).mean() for _ in range(5000)])
    boot_ci_lo, boot_ci_hi = np.percentile(boot_means, [2.5, 97.5])
    boot_p_le0 = float((boot_means <= 0).mean())

    mean_diff = diff.mean()
    se_diff = diff.std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
    t_stat = mean_diff / se_diff if se_diff and se_diff > 0 else float("nan")

    print(f"\n--- {label}: paired IC difference (candidate - live_equal_weight), n_months={n} ---")
    print(f"  mean diff: {mean_diff:.4f}   paired t: {t_stat:.2f}")
    print(f"  bootstrap 95% CI of mean diff: [{boot_ci_lo:.4f}, {boot_ci_hi:.4f}]")
    print(f"  bootstrap P(mean diff <= 0): {boot_p_le0:.3f}")
    print(f"  Wilcoxon signed-rank p-value: {wilcoxon_p:.4f}")

    return {"t_stat": t_stat, "wilcoxon_p": wilcoxon_p, "boot_p_le0": boot_p_le0, "mean_diff": mean_diff, "n": n}


def _era_split_check(live_ic: pd.Series, cand_ic: pd.Series, label: str) -> bool:
    common = sorted(live_ic.index.intersection(cand_ic.index))
    diff = (cand_ic.loc[common] - live_ic.loc[common])
    half = len(diff) // 2
    if half < 3:
        print(f"  {label}: too few OOS months to era-split - skipping robustness check")
        return False
    d1, d2 = diff.iloc[:half].mean(), diff.iloc[half:].mean()
    same_sign = bool((d1 > 0) == (d2 > 0))
    print(f"  {label}: first-half mean diff {d1:.4f}, second-half mean diff {d2:.4f}  -> {'SAME SIGN' if same_sign else 'DISAGREE'}")
    return same_sign


def build_oos_panel(start_date: str, end_date: str, min_cross_section: int) -> tuple[pd.DataFrame, list[Any]]:
    records_partial, _records_complete, _records_raw = build_pillar_proxy_records(
        start_date, end_date, min_cross_section
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
    oos = panel[panel["year"].isin(test_years)].copy()
    return oos, test_years


def add_candidate_predictions(oos: pd.DataFrame) -> pd.DataFrame:
    live_weight_map = {c: BASE_PILLAR_WEIGHTS[k] for c, k in PILLAR_TO_LIVE_KEY.items()}
    oos["pred_live"] = sum(oos[c] * w for c, w in live_weight_map.items())

    # DROP_GQ: Value+Risk+Momentum equal-thirds, Growth and Quality zeroed.
    oos["pred_drop_gq"] = (oos["value_proxy"] + oos["stability_proxy"] + oos["momentum_proxy"]) / 3.0

    # GARP_CAP gate, computed PER MONTH (no lookahead across months - each month's tercile
    # cutoff is computed only from that month's own cross-section, same discipline as every
    # other per-month normalization step in build_pillar_proxy_records).
    def _garp_value(g: pd.DataFrame) -> pd.Series:
        q_cut = g["quality_proxy"].quantile(GARP_GATE_PERCENTILE)
        r_cut = g["stability_proxy"].quantile(GARP_GATE_PERCENTILE)
        m_cut = g["momentum_proxy"].quantile(GARP_GATE_PERCENTILE)
        gate = (g["quality_proxy"] >= q_cut) & (g["stability_proxy"] >= r_cut) & (g["momentum_proxy"] >= m_cut)
        adj = g["value_proxy"].copy()
        adj[gate] = adj[gate].clip(lower=0.0)  # panel is z-scored, so 0.0 = that month's median
        return adj

    oos["value_proxy_garp"] = oos.groupby("month", group_keys=False).apply(_garp_value)
    oos["pred_garp"] = sum(
        oos[c if c != "value_proxy" else "value_proxy_garp"] * w for c, w in live_weight_map.items()
    )
    oos["pred_combined"] = (oos["value_proxy_garp"] + oos["stability_proxy"] + oos["momentum_proxy"]) / 3.0
    return oos


def run_statistical_tests(oos: pd.DataFrame) -> None:
    live_ic = _monthly_ic(oos, "pred_live")
    candidates = {
        "DROP_GQ (Value+Risk+Momentum only)": "pred_drop_gq",
        "GARP_CAP (Value floored under elite Q+R+M)": "pred_garp",
        "COMBINED (DROP_GQ + GARP_CAP)": "pred_combined",
    }

    print("\n########## PAIRED SIGNIFICANCE TESTS: each candidate vs live equal-weight ##########")
    t_stats: dict[str, float] = {}
    era_robust: dict[str, bool] = {}
    for label, col in candidates.items():
        cand_ic = _monthly_ic(oos, col)
        result = _paired_test(live_ic, cand_ic, label)
        t_stats[label] = result["t_stat"]
        era_robust[label] = _era_split_check(live_ic, cand_ic, label)

    print("\n########## FDR CORRECTION ACROSS THE 3-CANDIDATE FAMILY (q=0.10) ##########")
    n_months = len(live_ic)
    survives = benjamini_hochberg_fdr(t_stats, n_months, q=0.10)
    print(f"{'candidate':45s} {'t_stat':>8s} {'FDR-survives':>13s} {'era-robust':>11s} {'VERDICT':>10s}")
    for label in candidates:
        verdict = "CONFIRMED" if (survives[label] and era_robust[label]) else "not confirmed"
        print(f"{label:45s} {t_stats[label]:8.2f} {str(survives[label]):>13s} {str(era_robust[label]):>11s} {verdict:>10s}")

    print(
        "\nCONFIRMED requires BOTH FDR-corrected significance across the 3-candidate family AND"
        " the same-sign result in both halves of the OOS window - this file's own bar, matching"
        " every other confirmatory test in this repo's fama_macbeth_*.py family."
    )
    print(f"\nMean live_equal_weight monthly IC over the same OOS window: {live_ic.mean():.4f} (n={len(live_ic)} months)")


def run_megacap_rank_delta() -> None:
    print("\n########## ILLUSTRATIVE ONLY: mega-cap rank under each candidate, TODAY's live stock_scores ##########")
    print("(Not a significance test - shows what each candidate would concretely do to the symptom that motivated this test.)\n")
    with DatabaseContext("read") as cur:
        cur.execute(
            """
            SELECT symbol, quality_score, growth_score, value_score, risk_score, momentum_score, composite_score
            FROM stock_scores
            WHERE composite_score IS NOT NULL
            """
        )
        rows = cur.fetchall()
    df = pd.DataFrame(
        rows,
        columns=["symbol", "quality_score", "growth_score", "value_score", "risk_score", "momentum_score", "composite_score"],
    )
    for c in ["quality_score", "growth_score", "value_score", "risk_score", "momentum_score", "composite_score"]:
        df[c] = df[c].astype(float)

    df["drop_gq"] = (df["value_score"] + df["risk_score"] + df["momentum_score"]) / 3.0

    q_cut = df["quality_score"].quantile(GARP_GATE_PERCENTILE)
    r_cut = df["risk_score"].quantile(GARP_GATE_PERCENTILE)
    m_cut = df["momentum_score"].quantile(GARP_GATE_PERCENTILE)
    gate = (df["quality_score"] >= q_cut) & (df["risk_score"] >= r_cut) & (df["momentum_score"] >= m_cut)
    median_value = df["value_score"].median()
    df["value_score_garp"] = df["value_score"]
    df.loc[gate, "value_score_garp"] = df.loc[gate, "value_score"].clip(lower=median_value)
    df["garp"] = (
        0.20 * df["quality_score"]
        + 0.20 * df["growth_score"]
        + 0.20 * df["value_score_garp"]
        + 0.20 * df["risk_score"]
        + 0.20 * df["momentum_score"]
    )
    df["combined"] = (df["value_score_garp"] + df["risk_score"] + df["momentum_score"]) / 3.0

    n = len(df)

    def _rank(col: str, symbol: str) -> int:
        val = df.loc[df["symbol"] == symbol, col]
        if val.empty:
            return -1
        v = val.iloc[0]
        return int((df[col] > v).sum()) + 1

    print(f"Universe size: {n}")
    print(f"{'symbol':8s} {'live rank':>10s} {'DROP_GQ rank':>13s} {'GARP rank':>10s} {'COMBINED rank':>14s}")
    for sym in MEGACAP_SYMBOLS:
        if sym not in df["symbol"].values:
            print(f"{sym:8s}  (not found in stock_scores)")
            continue
        r_live = _rank("composite_score", sym)
        r_dgq = _rank("drop_gq", sym)
        r_garp = _rank("garp", sym)
        r_comb = _rank("combined", sym)
        print(f"{sym:8s} {r_live:10d} {r_dgq:13d} {r_garp:10d} {r_comb:14d}")


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    print_survivorship_bias_caveat()
    oos, test_years = build_oos_panel(start_date, end_date, min_cross_section)
    print(f"OOS test years: {test_years}, symbol-months: {len(oos)}")
    oos = add_candidate_predictions(oos)
    run_statistical_tests(oos)
    run_megacap_rank_delta()


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
