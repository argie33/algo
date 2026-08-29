#!/usr/bin/env python3
"""
Quality Real Estate reweight validation.

Built 2026-08-28 (goal: validate the PROPOSED FIX from
quality_component_sector_decomposition_20260828.py at the blended-formula level, before
building anything into a production loader). That script found, in isolation, that within
Real Estate specifically margin_volatility_3y (7% weight) is wrong-signed (t=-1.27,
Spearman IC=0.009) while ROE/ROA hold up fine (t=2.11/1.65). Isolated-component findings do
NOT automatically survive recombination into an actual weighted blend - this repo has
documented that exact "isolated vs joint" gap before (see MEMORY.md's "joint-dropna" lesson
applied to margin_volatility_3y, gross_profitability, book_value_growth elsewhere this
session). This script builds the actual candidate blends and tests them directly.

Reuses machinery from quality_component_sector_decomposition_20260828.py (sector map,
quality panel fetch/build, sign-adjusted COMPONENTS dict) and
growth_multi_input_blend_test_20260828.py (_renormalized_blend - z-score-and-weighted-average-
over-available, the same renormalization semantics the live _score_quality formula actually
uses).

Usage:
    python -m algo.research.quality_real_estate_reweight_validation_20260828 [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import _zwinsor
from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_momentum_factors import build_month_end_panel, compute_daily_indicators
from algo.research.fama_macbeth_momentum_factors import fetch_daily_prices as fetch_daily_close
from algo.research.fama_macbeth_price_factors import fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.growth_multi_input_blend_test_20260828 import _renormalized_blend
from algo.research.quality_component_sector_decomposition_20260828 import COMPONENTS
from algo.research.sector_relative_scoring_test_20260828 import UNCLASSIFIED, fetch_sector_map

logger = logging.getLogger(__name__)

MIN_SLICE = 10

# Nominal live weights (out of 101 - see loaders/load_value_quality_growth_metrics.py's
# quality_components comment). CURRENT is the live formula unchanged. DROP removes
# margin_volatility_3y entirely (its 7 points evaporate from the denominator, which
# _renormalized_blend's row_weight_sum already handles - the remaining 7 components'
# EFFECTIVE share grows proportionally on any row where margin_vol was going to be used
# anyway, matching "redistribute proportionally" without needing to hand-adjust their
# nominal weights). REWEIGHT removes margin_volatility_3y AND explicitly moves its 7 points
# onto ROE/ROA (the two components that showed real strength for Real Estate in the parent
# decomposition), split evenly.
WEIGHTS_CURRENT: dict[str, float] = {
    "roa": 18,
    "roce": 18,
    "debt_to_equity": 18,
    "fcf_margin": 15,
    "roe": 11,
    "margin_volatility_3y": 7,
    "asset_turnover": 7,
    "gross_profitability": 7,
}
WEIGHTS_DROP = {k: v for k, v in WEIGHTS_CURRENT.items() if k != "margin_volatility_3y"}
WEIGHTS_REWEIGHT = {
    **WEIGHTS_DROP,
    "roe": WEIGHTS_CURRENT["roe"] + 3.5,
    "roa": WEIGHTS_CURRENT["roa"] + 3.5,
}
VARIANTS: dict[str, dict[str, float]] = {"CURRENT": WEIGHTS_CURRENT, "DROP": WEIGHTS_DROP, "REWEIGHT": WEIGHTS_REWEIGHT}


def _fm_univariate(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> tuple[float, float, int]:
    coefs = []
    for _month, frame in records:
        sub = frame.dropna(subset=[col, "fwd_ret"])
        if len(sub) < MIN_SLICE or sub[col].std() == 0:
            continue
        x = np.column_stack([np.ones(len(sub)), sub[col].values])
        y = sub["fwd_ret"].values
        coef, *_ = np.linalg.lstsq(x, y, rcond=None)
        coefs.append(coef[1])
    if len(coefs) < 2:
        return (float("nan"), float("nan"), len(coefs))
    arr = np.array(coefs)
    se = arr.std(ddof=1) / np.sqrt(len(arr))
    return (arr.mean(), arr.mean() / se if se > 0 else float("nan"), len(coefs))


def _spearman_ic(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> tuple[float, float, int]:
    ics = []
    for _month, frame in records:
        sub = frame.dropna(subset=[col, "fwd_ret"])
        if len(sub) < MIN_SLICE:
            continue
        ic = sub[col].corr(sub["fwd_ret"], method="spearman")
        if ic is not None and not np.isnan(ic):
            ics.append(ic)
    if len(ics) < 2:
        return (float("nan"), float("nan"), len(ics))
    arr = np.array(ics)
    se = arr.std(ddof=1) / np.sqrt(len(arr))
    return (arr.mean(), arr.mean() / se if se > 0 else float("nan"), len(ics))


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Fetching sector map")
    sector_map = fetch_sector_map()

    logger.info("Building quality fundamentals panel")
    quality_raw = fetch_annual_quality_fundamentals()
    quality_fund = build_quality_panel(quality_raw)
    quality_fund = quality_fund.merge(
        quality_raw[["symbol", "fiscal_year", "revenue", "total_assets"]], on=["symbol", "fiscal_year"], how="left"
    )
    quality_fund["asset_turnover"] = np.where(
        quality_fund["total_assets"] > 0, quality_fund["revenue"] / quality_fund["total_assets"], np.nan
    )

    logger.info("Fetching price panel")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)
    months = px.index

    daily_close = fetch_daily_close(start_date, end_date)
    daily_close = compute_daily_indicators(daily_close)
    build_month_end_panel(daily_close)  # not used here, kept for parity/side-effect-free call

    quality_monthly = merge_asof_monthly(months, quality_fund, cols=list(COMPONENTS.keys()))

    all_records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(1, len(months) - 1):
        month = months[i]
        q = quality_monthly.get(month)
        if q is None or q.empty:
            continue
        fwd_ret = ret.iloc[i + 1].reindex(q.index)
        frame = pd.DataFrame({c: sign * q[c] for c, sign in COMPONENTS.items()}, index=q.index)
        frame["fwd_ret"] = fwd_ret
        frame["sector"] = sector_map.reindex(q.index).fillna(UNCLASSIFIED)
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        all_records.append((month, frame))

    if not all_records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(all_records)}  ({all_records[0][0]} to {all_records[-1][0]})")

    def _build_blend_records(sector_filter: str | None) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
        """Z-score each raw component (winsorized, cross-sectionally, on the FULL universe
        each month so blends stay comparable across slices), build all 3 blend variants,
        then optionally slice down to one sector. Z-scoring on the full universe (not just
        the sector subset) matches how the live formula actually works - it does not
        recompute a sector-local z-score, it uses one universal curve/scale."""
        out = []
        for month, frame in all_records:
            z = pd.DataFrame({c: _zwinsor(frame[c]) for c in COMPONENTS}, index=frame.index)
            blend_frame = pd.DataFrame(index=frame.index)
            for name, weights in VARIANTS.items():
                blend_frame[name] = _renormalized_blend(z[list(weights.keys())], weights)
            blend_frame["fwd_ret"] = frame["fwd_ret"]
            blend_frame["sector"] = frame["sector"]
            if sector_filter is not None:
                blend_frame = blend_frame[blend_frame["sector"] == sector_filter]
            if len(blend_frame) >= MIN_SLICE:
                out.append((month, blend_frame))
        return out

    re_records = _build_blend_records("Real Estate")
    full_records = _build_blend_records(None)

    re_cov = [len(f) for _m, f in re_records]
    print(f"Real Estate usable months: {len(re_records)}  (median {int(np.median(re_cov))} symbols/month)\n")

    def _report(label: str, records: list[tuple[pd.Timestamp, pd.DataFrame]]) -> None:
        split_idx = len(records) // 2
        halves = {"FULL": records, "ERA1": records[:split_idx], "ERA2": records[split_idx:]}
        print(f"=== {label}: Fama-MacBeth univariate t-stat ===")
        print(f"{'variant':10s}{'FULL':>12s}{'ERA1':>12s}{'ERA2':>12s}")
        for variant in VARIANTS:
            row = f"{variant:10s}"
            for era in halves.values():
                _mean, t, _n = _fm_univariate(era, variant)
                row += f"{t:12.2f}" if not np.isnan(t) else f"{'n/a':>12s}"
            print(row)
        print(f"\n=== {label}: Spearman IC ===")
        print(f"{'variant':10s}{'FULL':>12s}{'ERA1':>12s}{'ERA2':>12s}")
        for variant in VARIANTS:
            row = f"{variant:10s}"
            for era in halves.values():
                mean_ic, _t, _n = _spearman_ic(era, variant)
                row += f"{mean_ic:12.4f}" if not np.isnan(mean_ic) else f"{'n/a':>12s}"
            print(row)
        print()

    _report("Real Estate only", re_records)
    _report("Full universe (sanity check: would DROP/REWEIGHT help or hurt everyone else?)", full_records)


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
