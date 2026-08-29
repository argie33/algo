#!/usr/bin/env python3
"""
Does Growth's live fixed-curve construction (_score_single_growth, cap-at-30%-per-field) lose to
cross-sectional percentile ranking, the same way Value's P/E/P/B/P/S already did?

Built 2026-08-28 (goal: "do the same [industry-standard-alignment review] with the growth...
maybe we need to do things certain ways to get the growth candidates best identified"). This is
NOT a re-test of which fields belong in Growth or whether they should be sign-flipped - both were
already explicitly re-litigated and settled by user directive earlier the same day (see
_score_growth's own "RESTORED TO MULTI-INPUT 2026-08-28" docstring note in
loaders/load_stock_scores.py - multi-input, NOT sign-flipped, explicit override of this repo's
own growth-reversal research). This script tests a narrower, orthogonal question: given the same
field set and the same sign convention, does the SHAPE of each field's individual score (a fixed
absolute cap-based curve vs. a cross-sectional percentile rank against the current universe)
matter - the identical question already answered for Value's three multiples in
algo/research/value_absolute_curve_vs_relative_ranking_20260828.py (cross-sectional percentile
won in every era/spec tested there) and already implemented for real in
loaders/load_stock_scores.py's update_value_multiples_percentiles()/update_rs_percentiles().

Reuses algo/research/fama_macbeth_growth_factors.py's existing point-in-time panel machinery
(fetch_annual_fundamentals/build_growth_panel/merge_asof_monthly) rather than rebuilding it - see
that module's own docstring for the point-in-time reporting-lag caveat, which applies here
unchanged. Tests the 10 of GROWTH_SCORE_FIELDS's 15 live inputs reconstructable from annual
statement data (eps/revenue growth 1y/3y/5y, net_income/operating_income growth yoy, fcf/ocf
growth yoy, asset growth yoy) - sustainable_growth_rate/quarterly_growth_momentum/
earnings_growth_4q_avg need quarterly-cadence data this panel doesn't reconstruct, out of scope
here, not a claim they don't matter.

IMPORTANT: asset_growth_yoy is tested UNFLIPPED (raw growth, "higher=better"), matching the LIVE
production sign convention after the same-day user override - NOT
fama_macbeth_growth_factors.py's own asset_growth_yoy_flipped column, which predates that
override and uses the literature-standard inverted sign for that script's own separate purposes.

Usage:
    python -m algo.research.growth_fixed_curve_vs_relative_ranking_20260828 [options]
"""

import argparse
import logging
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

# The 10 of GROWTH_SCORE_FIELDS reconstructable from annual statement data - see module
# docstring for the 5 excluded (quarterly-cadence fields this panel can't reach) and for why
# asset_growth_yoy is unflipped here.
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

# build_growth_panel() only produces asset_growth_yoy_flipped (literature-standard inverted
# sign, for that script's own separate purposes) - fetch that column and negate it back to the
# live production (unflipped, "higher=better") convention, see module docstring.
_PANEL_COLS = [f for f in FIELDS if f != "asset_growth_yoy"] + ["asset_growth_yoy_flipped"]


def _score_single_growth_pct(val_decimal: float, cap_pct: float = 30.0) -> float:
    """Byte-for-byte replica of loaders/load_stock_scores.py's _score_single_growth, applied to
    a decimal growth rate (this panel's convention) instead of a percentage-point one (live
    production's convention) - multiplies by 100 first to match."""
    val = val_decimal * 100.0
    if val <= 0:
        return max(0.0, 40 + (val / 50) * 40)
    return min(100.0, 40 + (val / cap_pct) * 60)


def _percent_rank_higher_is_better(values: dict[str, float]) -> dict[str, float]:
    """symbol -> percentile in [0, 100], HIGHEST raw growth gets HIGHEST percentile (unlike
    Value's cheap-is-good convention, growth is already higher-is-better after the live
    not-sign-flipped override, so no inversion needed)."""
    n = len(values)
    if n == 0:
        return dict()  # noqa: C408 - not a silent fallback: pure function, empty input has nothing to rank; see check-silent-fallbacks.py's literal "return {}" pattern match
    if n == 1:
        return dict.fromkeys(values, 50.0)
    sorted_items = sorted(values.items(), key=lambda kv: kv[1])
    result: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j < n and sorted_items[j][1] == sorted_items[i][1]:
            j += 1
        pct = 100.0 * i / (n - 1)  # lowest raw value -> 0, highest -> 100
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

    fixed_records = []
    pct_records = []
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

        # Cross-sectional percentile rank, computed independently per field (same "partial
        # availability, rank what exists" pattern as update_value_multiples_percentiles()).
        field_pct: dict[str, dict[str, float]] = {}
        for field in FIELDS:
            raw = cross_section[field].dropna()
            field_pct[field] = _percent_rank_higher_is_better(raw.to_dict())

        for symbol, row in cross_section.iterrows():
            ret = fwd_ret.get(symbol)
            if ret is None or pd.isna(ret):
                continue

            fixed_scores = [_score_single_growth_pct(row[f]) for f in FIELDS if pd.notna(row[f])]
            pct_scores = [field_pct[f][symbol] for f in FIELDS if pd.notna(row[f]) and symbol in field_pct[f]]
            if not fixed_scores or not pct_scores:
                continue

            fixed_records.append({"symbol": symbol, "month": month, "score": np.mean(fixed_scores), "fwd_ret": ret})
            pct_records.append({"symbol": symbol, "month": month, "score": np.mean(pct_scores), "fwd_ret": ret})

    fixed_df = pd.DataFrame(fixed_records)
    pct_df = pd.DataFrame(pct_records)
    if fixed_df.empty or pct_df.empty:
        raise RuntimeError("No usable cross-sectional months - check fundamentals coverage / date range")
    logger.info(f"Usable months: fixed={fixed_df['month'].nunique()}, percentile={pct_df['month'].nunique()}")

    def _fm_ic(df: pd.DataFrame, label: str) -> None:
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

    def _fm_regression(df: pd.DataFrame, label: str) -> None:
        # Direct per-month Fama-MacBeth: regress fwd_ret on z-scored score, average the
        # monthly coefficients. Single-factor case, so this is equivalent to _fama_macbeth's
        # own multi-factor machinery without needing its DataFrame-per-month plumbing.
        coefs = []
        for _month, g in df.groupby("month"):
            if len(g) < min_cross_section:
                continue
            z = (g["score"] - g["score"].mean()) / g["score"].std(ddof=0)
            valid = z.notna() & g["fwd_ret"].notna()
            if valid.sum() < min_cross_section:
                continue
            coef = np.polyfit(z[valid], g["fwd_ret"][valid], 1)[0]
            coefs.append(coef)
        arr = np.array(coefs)
        t_stat = arr.mean() / (arr.std(ddof=1) / np.sqrt(len(arr))) if len(arr) > 1 else float("nan")
        print(f"{label}: mean coef={arr.mean():.5f}, t={t_stat:.2f}, n_months={len(arr)}")

    print("\n=== FULL SAMPLE ===")
    _fm_ic(fixed_df, "Fixed curve  (IC)")
    _fm_ic(pct_df, "Percentile   (IC)")
    _fm_regression(fixed_df, "Fixed curve  (FM coef)")
    _fm_regression(pct_df, "Percentile   (FM coef)")

    months_sorted = sorted(fixed_df["month"].unique())
    mid = months_sorted[len(months_sorted) // 2]
    for label, lo, hi in [("FIRST HALF", months_sorted[0], mid), ("SECOND HALF", mid, months_sorted[-1])]:
        print(f"\n=== {label} ({lo} to {hi}) ===")
        _fm_ic(fixed_df[(fixed_df["month"] >= lo) & (fixed_df["month"] <= hi)], "Fixed curve  (IC)")
        _fm_ic(pct_df[(pct_df["month"] >= lo) & (pct_df["month"] <= hi)], "Percentile   (IC)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    args = parser.parse_args()
    run(args.start_date, args.end_date, args.min_cross_section)


if __name__ == "__main__":
    main()
