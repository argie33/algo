#!/usr/bin/env python3
"""
Design/validate a CONTINUOUS ROA-conditioned interaction feature for net_margin and
gross_profitability, to replace the discrete-tercile evidence in
quality_margin_interaction_check.py (MEMORY.md: quality_net_margin_roa_interaction_effect_found_
20260826, quality_low_roa_interaction_pattern_across_candidates_20260826) with something that can
actually be scored per-symbol in the live loader - stock_scores.

Why not just use terciles directly in production: the tercile boundary is a hard, gameable
discontinuity (a firm just above/below the universe's roa cutoff for that month gets a
completely different treatment), and it requires knowing the full cross-section's ROA
distribution at scoring time, which the per-symbol loader (load_value_quality_growth_metrics.py)
doesn't have. A continuous interaction TERM (candidate_z * roa_z, both cross-sectionally
z-scored) is the textbook way to represent "this candidate's effect changes linearly with roa" -
no threshold, and its regression coefficient tells us directly whether that's actually the right
functional form for what quality_margin_interaction_check.py found empirically as three
tercile buckets.

Test: each month, regress fwd_ret on [const, roa_z, candidate_z, roa_z*candidate_z] jointly
(not the tercile split), Fama-MacBeth average across months. A significant, correctly-signed
interaction coefficient means the SAME linear-interaction feature (candidate_z * roa_z) that
gets built here is a valid continuous stand-in for the tercile finding. Then half-split
(2014-2020 vs 2020-2026) checked the same way as every other Quality component change this
project makes before touching live scoring.

Usage:
    python -m algo.research.quality_roa_interaction_feature_design
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals

logger = logging.getLogger(__name__)

CANDIDATES = ["net_margin", "gross_profitability"]


def _zscore_cross_section(frame: pd.DataFrame, col: str) -> pd.Series:
    lo, hi = frame[col].quantile([0.01, 0.99])
    clipped = frame[col].clip(lo, hi)
    std = clipped.std()
    return (clipped - clipped.mean()) / std if std > 0 else clipped * 0.0


def _roa_score_curve(roa: pd.Series) -> pd.Series:
    """Reproduces load_value_quality_growth_metrics.py's actual live roa_score curve exactly
    (_margin_curve(roa, [(3.0,40.0),(8.0,80.0),(15.0,100.0)])) - NOT a cross-sectional
    percentile rank. This loader scores one symbol at a time with no access to the rest of the
    universe's ROA distribution in the same call (unlike rs_percentile, which gets a separate
    batch PERCENT_RANK() post_run() pass over the whole table) - a percentile-based conditioning
    variable is a research convenience that doesn't correspond to anything deployable in
    production. roa_score is: fixed absolute breakpoints, computed per-symbol, already exists
    live - using it as the conditioning variable means the validated feature IS the production
    feature, not an approximation of it."""
    x0, y0 = 3.0, 40.0
    x1, y1 = 8.0, 80.0
    x2, y2 = 15.0, 100.0

    def curve(v: float) -> float:
        if pd.isna(v) or v < 0:
            return 0.0
        if v < x0:
            return (v / x0) * y0
        if v < x1:
            return y0 + (v - x0) / (x1 - x0) * (y1 - y0)
        if v < x2:
            return y1 + (v - x1) / (x2 - x1) * (y2 - y1)
        return 100.0

    return roa.apply(curve)


def _sign_flip_multiplier(roa_pctile: pd.Series) -> pd.Series:
    """+1 at roa_pctile=0 (worst ROA) -> 0 at roa_pctile=50 -> -1 at roa_pctile=100 (best ROA).
    Matches net_margin/accruals_ratio's confirmed tercile shape (positive low-ROA, ~flat
    mid-ROA, negative high-ROA) with no hard threshold."""
    return 1.0 - (roa_pctile / 50.0)


def _fade_multiplier(roa_pctile: pd.Series) -> pd.Series:
    """+1 at roa_pctile=0 decaying linearly to 0 by roa_pctile=50, flat 0 beyond. Matches
    gross_profitability's confirmed tercile shape (strong low-ROA, ~zero mid/high-ROA - not a
    sign flip, a fade)."""
    return (1.0 - (roa_pctile / 50.0)).clip(lower=0.0)


MULTIPLIERS = {
    "net_margin": _sign_flip_multiplier,
    "gross_profitability": _fade_multiplier,
}


def build_monthly_records(
    start_date: str, end_date: str, min_cross_section: int
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    fund = fetch_annual_quality_fundamentals()
    quality_panel = build_quality_panel(fund)

    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly = merge_asof_monthly(months, quality_panel, cols=["roa", *CANDIDATES])

    records = []
    for i in range(len(months) - 1):
        month = months[i]
        qframe = monthly.get(month)
        if qframe is None or qframe.empty:
            continue
        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        frame = qframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        frame = frame.dropna(subset=["roa", *CANDIDATES])
        if len(frame) < min_cross_section:
            continue

        out = frame[["fwd_ret"]].copy()
        # fama_macbeth_quality_factors.build_quality_panel's roa is a raw ratio
        # (net_income/total_assets); the live loader's roa_score curve (and metrics["roa"]
        # itself) is calibrated in PERCENTAGE POINTS (net_income/total_assets * 100, see
        # load_value_quality_growth_metrics.py's computed_roa). Must rescale here or the curve's
        # breakpoints (3.0/8.0/15.0) silently see almost every real-world ratio as ~0 - caught
        # live during this validation (multiplier was landing at ~1.0 for 99.97% of rows,
        # correlation 0.999 with the unconditioned raw signal, before this fix).
        roa_score = _roa_score_curve(frame["roa"] * 100.0)
        out["roa_z"] = _zscore_cross_section(frame, "roa")
        for c in CANDIDATES:
            c_z = _zscore_cross_section(frame, c)
            out[f"{c}_z"] = c_z
            out[f"{c}_adj"] = c_z * MULTIPLIERS[c](roa_score)
        records.append((month, out))
    return records


def _run_and_print(label: str, records: list[tuple[pd.Timestamp, pd.DataFrame]]) -> None:
    """The production-relevant test: roa is ALREADY an 18%-weighted live component, so what
    matters is whether a candidate adds INCREMENTAL signal once roa_z is controlled for
    (matching how memory's original net_margin verdict, t=-0.08, was itself a MULTIVARIATE
    result - a univariate-only comparison would just re-litigate a different question)."""
    print(f"--- {label} ({len(records)} months) ---")
    for c in CANDIDATES:
        for cand_col, tag in (
            (f"{c}_z", "raw, controlling for roa_z"),
            (f"{c}_adj", "ROA-adjusted, controlling for roa_z"),
        ):
            result = _fama_macbeth(records, ["roa_z", cand_col])
            mean, t = result[cand_col]
            print(f"  {c:20s} {tag:36s} mean_coef={mean:10.5f}  t_stat={t:7.2f}")
    print()


def run(start_date: str, end_date: str, min_cross_section: int, split_date: str) -> None:
    logger.info(f"Building monthly records {start_date}..{end_date}")
    records = build_monthly_records(start_date, end_date, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})\n")
    _run_and_print("FULL SAMPLE", records)

    split_ts = pd.Timestamp(split_date)
    first_half = [r for r in records if pd.Timestamp(r[0]) < split_ts]
    second_half = [r for r in records if pd.Timestamp(r[0]) >= split_ts]
    _run_and_print(f"FIRST HALF (< {split_date})", first_half)
    _run_and_print(f"SECOND HALF (>= {split_date})", second_half)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--split-date", default="2020-06-01", help="Half-split boundary (matches prior Quality checks)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.split_date)


if __name__ == "__main__":
    main()
