#!/usr/bin/env python3
"""
Quality component sector decomposition.

Built 2026-08-28 (goal: decompose WHY the blended quality_proxy's Spearman IC is 3-5x weaker
and non-significant specifically for Financial Services (IC=0.0118, t=1.37) and Real Estate
(IC=0.0073, t=0.81) vs everyone else (IC=0.0363, t=4.67) - a finding from
algo/research/sector_relative_scoring_test_20260828.py that script could not attribute to any
single one of Quality's 8 live components. Reuses that script's sector map, quality-panel
fetch/build functions, and Fama-MacBeth/Spearman-IC machinery directly - no re-derivation.

METHODOLOGY NOTE (departs from the parent script's 0-fill convention deliberately): the parent
script z-scores then `.fillna(0.0)` each proxy component before building `records`, which is
necessary there because its multivariate regression needs every column non-null on every row
simultaneously. That convention is WRONG for this script's purpose: 0-filling a component that's
structurally absent for a sector (gross_profitability: 15.5%/34.9% coverage for Financial
Services/Real Estate) would mechanically pin ~65-85% of that sector's rows at a synthetic
"average" value, silently diluting the component's own measured IC rather than revealing whether
its real, present values (the 15.5%/34.9% that exist) carry signal or not - and it would misrepresent
how the LIVE formula actually treats a missing component (renormalizes the weighted average over
whatever IS present, i.e. that company is simply absent from that term - not present-at-zero).
This script therefore does a plain per-component dropna instead: each component's univariate
regression/IC uses only the symbol-months where that specific raw component is non-null, matching
the live renormalization's actual semantics.

Usage:
    python -m algo.research.quality_component_sector_decomposition_20260828 [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_momentum_factors import build_month_end_panel, compute_daily_indicators
from algo.research.fama_macbeth_momentum_factors import fetch_daily_prices as fetch_daily_close
from algo.research.fama_macbeth_price_factors import fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.sector_relative_scoring_test_20260828 import UNCLASSIFIED, fetch_sector_map

logger = logging.getLogger(__name__)

FOCUS_SECTORS = ["Financial Services", "Real Estate"]
MIN_SLICE = 10

# component -> sign. sign=-1 means "lower is better" in the live _score_quality formula
# (debt_to_equity, margin_volatility_3y) - negate BEFORE any z-score/correlation so a positive
# coefficient/IC always means "more of this signal -> higher forward return", consistent
# direction across all 8 for readability.
COMPONENTS = {
    "roe": 1,
    "roa": 1,
    "roce": 1,
    "fcf_margin": 1,
    "debt_to_equity": -1,
    "margin_volatility_3y": -1,
    "asset_turnover": 1,
    "gross_profitability": 1,
}


def _fm_univariate_dropna(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> tuple[float, float, int]:
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


def _spearman_ic_dropna(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> tuple[float, float, int]:
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

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
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
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    for focus in FOCUS_SECTORS:
        cov = [int((f["sector"] == focus).sum()) for _, f in records]
        print(f"  {focus}: median {int(np.median(cov))} symbols/month")
    print()

    slices = {
        "Financial Services": [(m, f[f["sector"] == "Financial Services"]) for m, f in records],
        "Real Estate": [(m, f[f["sector"] == "Real Estate"]) for m, f in records],
        "Everyone else": [(m, f[~f["sector"].isin(FOCUS_SECTORS)]) for m, f in records],
    }

    # Coverage of each raw component within each slice (non-null rate, pooled across months) -
    # answers "is this component even present enough in this sector to test", independent of
    # whether it turns out predictive.
    print("=== Raw component coverage (non-null %) by sector slice ===")
    header = f"{'component':22s}" + "".join(f"{lbl:>20s}" for lbl in slices)
    print(header)
    for comp in COMPONENTS:
        row = f"{comp:22s}"
        for _label, sliced in slices.items():
            all_rows = pd.concat([f[comp] for _m, f in sliced]) if sliced else pd.Series(dtype=float)
            pct = 100.0 * all_rows.notna().mean() if len(all_rows) else float("nan")
            row += f"{pct:19.1f}%"
        print(row)
    print()

    print("=== Univariate Fama-MacBeth t-stat (dropna per component, sign-adjusted so + = good) ===")
    header = f"{'component':22s}" + "".join(f"{lbl:>20s}" for lbl in slices)
    print(header)
    t_table: dict[str, dict[str, float]] = {c: {} for c in COMPONENTS}
    for comp in COMPONENTS:
        row = f"{comp:22s}"
        for label, sliced in slices.items():
            sliced_min = [(m, f) for m, f in sliced if len(f) >= MIN_SLICE]
            _mean, t, n = _fm_univariate_dropna(sliced_min, comp)
            t_table[comp][label] = t
            row += f"{t:17.2f}(n={n:<3d})" if not np.isnan(t) else f"{'n/a':>20s}"
        print(row)
    print()

    print("=== Spearman IC (dropna per component, sign-adjusted so + = good) ===")
    print(header)
    ic_table: dict[str, dict[str, float]] = {c: {} for c in COMPONENTS}
    for comp in COMPONENTS:
        row = f"{comp:22s}"
        for label, sliced in slices.items():
            sliced_min = [(m, f) for m, f in sliced if len(f) >= MIN_SLICE]
            mean_ic, _t, n = _spearman_ic_dropna(sliced_min, comp)
            ic_table[comp][label] = mean_ic
            row += f"{mean_ic:17.4f}(n={n:<3d})" if not np.isnan(mean_ic) else f"{'n/a':>20s}"
        print(row)


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
