#!/usr/bin/env python3
"""
Re-validates margin_volatility_3y as a Quality candidate, 2026-08-27.

Context: margin_volatility_3y (trailing-3yr stdev of net_margin, a QMJ "Safety" leg proxy) was
REMOVED from live Quality scoring 2026-08-26 on a weak pooled UNIVARIATE linear test
(t=-1.28/-1.51, see MEMORY.md quality_pillar_composite_rebuilt_roce_fcf_margin_d2e_20260826).
A later systematic SHAP interaction sweep (quality_shap_interaction_sweep.py) found
margin_volatility_3y has the HIGHEST main-effect ML importance of any Quality candidate -
higher than roa, which is live at 18% weight - and appears in 6 of the top 25 interaction
pairs (see MEMORY.md quality_shap_interaction_sweep_built_margin_volatility_3y_flagged_20260827).
That sweep explicitly did NOT validate a deployable signed feature - it only ranked interaction
strength. This script closes that gap with the same discipline as every other Quality decision:
full-sample + half-split Fama-MacBeth, both univariate and controlling for the 7 live Quality
components (roa/roce/debt_to_equity/fcf_margin/roe/interest_coverage/payout_ratio) jointly - a
candidate that only "works" once the live components are NOT controlled for would just be
proxying for something already scored, not adding incremental signal.

If the raw form doesn't clear this repo's established bar (|t|>~2 full-sample AND reasonably
consistent across the half-split - see quality_roa_interaction_feature_design.py's precedent),
also tests an ROA-conditioned version the same way that script did for net_margin/
gross_profitability, reusing the live roa_score curve as the (deployable, per-symbol) conditioning
variable.

Usage:
    python -m algo.research.quality_margin_volatility_revalidation
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

CANDIDATE = "margin_volatility_3y"
# The 7 live Quality components (loaders/load_value_quality_growth_metrics.py quality_components,
# migration 1238 + the 2026-08-26 Altman Z removal - see MEMORY.md
# quality_pillar_composite_rebuilt_roce_fcf_margin_d2e_20260826).
LIVE_COLS = ["roa", "roce", "debt_to_equity", "fcf_margin", "roe", "interest_coverage", "payout_ratio"]


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def _roa_score_curve(roa_pct: pd.Series) -> pd.Series:
    """Reproduces load_value_quality_growth_metrics.py's live roa_score curve exactly
    (_margin_curve(roa, [(3.0,40.0),(8.0,80.0),(15.0,100.0)])), same as
    quality_roa_interaction_feature_design.py's own copy of this curve. Input MUST be in
    percentage points (roa*100), not the raw ratio - that script's own hard-won bug fix."""
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

    return roa_pct.apply(curve)


def build_records(start_date: str, end_date: str, min_cross_section: int) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    fund = fetch_annual_quality_fundamentals()
    quality_panel = build_quality_panel(fund)

    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly = merge_asof_monthly(months, quality_panel, cols=[CANDIDATE, *LIVE_COLS])

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
        # multivariate control test needs ALL 7 live cols + candidate present that month
        frame = frame.dropna(subset=[CANDIDATE, *LIVE_COLS])
        if len(frame) < min_cross_section:
            continue

        out = frame[["fwd_ret"]].copy()
        for c in [CANDIDATE, *LIVE_COLS]:
            out[c] = _zwinsor(frame[c])
        # ROA-conditioned version - same construction as quality_roa_interaction_feature_design.py.
        # quality_panel's roa is a raw ratio (net_income/total_assets); the live curve is
        # calibrated in percentage points - must rescale by *100 before the curve breakpoints
        # (3.0/8.0/15.0), same bug that script caught.
        roa_score = _roa_score_curve(frame["roa"] * 100.0)
        roa_pctile = roa_score.rank(pct=True) * 100.0
        sign_flip = 1.0 - (roa_pctile / 50.0)
        out[f"{CANDIDATE}_roa_adj"] = out[CANDIDATE] * sign_flip
        records.append((month, out))
    return records


def _run_and_print(label: str, records: list[tuple[pd.Timestamp, pd.DataFrame]]) -> None:
    print(f"--- {label} ({len(records)} months) ---")
    uni = _fama_macbeth(records, [CANDIDATE])
    mean, t = uni[CANDIDATE]
    print(f"  {CANDIDATE:24s} univariate                          mean_coef={mean:10.5f}  t_stat={t:7.2f}")

    multi = _fama_macbeth(records, [*LIVE_COLS, CANDIDATE])
    mean, t = multi[CANDIDATE]
    print(f"  {CANDIDATE:24s} controlling for 7 live components   mean_coef={mean:10.5f}  t_stat={t:7.2f}")

    multi_adj = _fama_macbeth(records, [*LIVE_COLS, f"{CANDIDATE}_roa_adj"])
    mean, t = multi_adj[f"{CANDIDATE}_roa_adj"]
    print(f"  {CANDIDATE:24s} ROA-adjusted, controlling for 7 live mean_coef={mean:10.5f}  t_stat={t:7.2f}")
    print()


def run(start_date: str, end_date: str, min_cross_section: int, split_date: str) -> None:
    logger.info(f"Building monthly records {start_date}..{end_date}")
    records = build_records(start_date, end_date, min_cross_section)
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
