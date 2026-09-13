#!/usr/bin/env python3
"""Research-only, one-off: does Quality's floor-negative-to-0-then-sector-zscore ROA transform
(current production, vqg_quality_batch.py) beat a continuous sector-neutral z-score with no
floor, on real forward-return predictive power? Also checks whether sector membership itself
has real, era-robust forward-return predictive power (if not, the current transform's sector
skew isn't earning its keep). Fit 2017-2021 / holdout 2022-2026, same discipline as
composite_percentile_and_interaction_test_20260831.py and the dividend K-sensitivity check.

Not wired into any test suite or production path - throwaway research script, scratch/ per
this repo's own convention (see CLAUDE.md's monthly-cleanup section).
"""

import logging

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import (
    _fama_macbeth,
    fetch_month_end_prices,
    print_survivorship_bias_caveat,
)
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from loaders.helpers.factor_normalization import sector_neutral_zscore, zscore_to_percentile_scale
from loaders.helpers.vqg_shared import apply_mortgage_reit_sector_override
from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.WARNING)


def fetch_sector_map() -> dict[str, str]:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol, sector FROM company_profile WHERE sector IS NOT NULL")
        return {row[0]: apply_mortgage_reit_sector_override(row[0], row[1]) or row[1] for row in cur.fetchall()}


def build_records(months, px, panel, sector_map, horizon_months=1, min_cross_section=100):
    monthly = merge_asof_monthly(months, panel, cols=["roa"])
    records = []
    for i in range(len(months) - horizon_months):
        month = months[i]
        qframe = monthly.get(month)
        if qframe is None or qframe.empty:
            continue
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = qframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        symbols = list(frame.index)
        sectors = {s: sector_map[s] for s in symbols if s in sector_map}
        raw_roa = {s: float(frame.loc[s, "roa"]) for s in symbols}

        nonneg_roa = {s: v for s, v in raw_roa.items() if v >= 0.0}
        floor_pct = zscore_to_percentile_scale(sector_neutral_zscore(nonneg_roa, sectors))
        frame["floor_then_zscore"] = [floor_pct.get(s, 0.0) if raw_roa[s] >= 0 else 0.0 for s in symbols]

        continuous_pct = zscore_to_percentile_scale(sector_neutral_zscore(raw_roa, sectors))
        frame["continuous_zscore"] = [continuous_pct.get(s, 50.0) for s in symbols]

        lo, hi = frame["roa"].quantile([0.01, 0.99])
        frame["raw_roa_z"] = frame["roa"].clip(lo, hi)
        std = frame["raw_roa_z"].std()
        frame["raw_roa_z"] = (frame["raw_roa_z"] - frame["raw_roa_z"].mean()) / std if std > 0 else 0.0

        for col in ("floor_then_zscore", "continuous_zscore"):
            m, s = frame[col].mean(), frame[col].std()
            frame[col] = (frame[col] - m) / s if s > 0 else 0.0

        frame["sector"] = [sectors.get(s, "Unknown") for s in symbols]
        records.append((month, frame))
    return records


def sector_dummy_fm(records, sectors_universe):
    """FM regression of fwd_ret on sector dummies (drop-first), to check whether sector
    membership itself carries real, era-robust forward-return predictive power."""
    coef_hist = {sec: [] for sec in sectors_universe[1:]}
    for _month, frame in records:
        x_cols = []
        for sec in sectors_universe[1:]:
            x_cols.append((frame["sector"] == sec).astype(float).values)
        x = np.column_stack([np.ones(len(frame)), *x_cols])
        y = frame["fwd_ret"].values
        coefs, *_ = np.linalg.lstsq(x, y, rcond=None)
        for j, sec in enumerate(sectors_universe[1:], start=1):
            coef_hist[sec].append(coefs[j])
    out = {}
    for sec, series in coef_hist.items():
        arr = np.array(series)
        mean = arr.mean()
        se = arr.std(ddof=1) / np.sqrt(len(arr)) if len(arr) > 1 else np.nan
        out[sec] = (mean, mean / se if se and se > 0 else float("nan"))
    return out


def split_records(records, fit_end, holdout_start):
    fit = [(m, f) for m, f in records if pd.Timestamp(m) < pd.Timestamp(fit_end)]
    holdout = [(m, f) for m, f in records if pd.Timestamp(m) >= pd.Timestamp(holdout_start)]
    return fit, holdout


def main():
    print_survivorship_bias_caveat()
    fund = fetch_annual_quality_fundamentals()
    panel = build_quality_panel(fund)[["symbol", "fiscal_year", "roa", "known_date"]].dropna(subset=["roa"])
    sector_map = fetch_sector_map()

    price_df = fetch_month_end_prices("2014-01-01", "2026-09-01")
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    records = build_records(months, px, panel, sector_map)
    print(f"Usable cross-sectional months: {len(records)} ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median([len(f) for _, f in records]))}\n")

    fit, holdout = split_records(records, "2022-01-01", "2022-01-01")
    print(f"Fit (2017-2021-ish, pre-2022): {len(fit)} months. Holdout (2022+): {len(holdout)} months.\n")

    print("=== floor_then_zscore (current production ROA transform) ===")
    for label, recs in (("FIT", fit), ("HOLDOUT", holdout), ("FULL", records)):
        mean, t = _fama_macbeth(recs, ["floor_then_zscore"])["floor_then_zscore"]
        print(f"  {label:8s} mean_coef={mean:9.5f}  t={t:6.2f}  n_months={len(recs)}")

    print("\n=== continuous_zscore (no floor, full sector population) ===")
    for label, recs in (("FIT", fit), ("HOLDOUT", holdout), ("FULL", records)):
        mean, t = _fama_macbeth(recs, ["continuous_zscore"])["continuous_zscore"]
        print(f"  {label:8s} mean_coef={mean:9.5f}  t={t:6.2f}  n_months={len(recs)}")

    print("\n=== raw_roa_z (universe-wide, not sector-neutral at all - sanity check) ===")
    for label, recs in (("FIT", fit), ("HOLDOUT", holdout), ("FULL", records)):
        mean, t = _fama_macbeth(recs, ["raw_roa_z"])["raw_roa_z"]
        print(f"  {label:8s} mean_coef={mean:9.5f}  t={t:6.2f}  n_months={len(recs)}")

    print("\n=== Multivariate: floor_then_zscore + continuous_zscore jointly (collinearity check) ===")
    multi = _fama_macbeth(records, ["floor_then_zscore", "continuous_zscore"])
    for name, (mean, t) in multi.items():
        print(f"  {name:20s} mean_coef={mean:9.5f}  t={t:6.2f}")

    print("\n=== Does SECTOR MEMBERSHIP itself predict forward returns? (FM on sector dummies) ===")
    sectors_universe = sorted({sec for _, f in records for sec in f["sector"].unique()})
    print(f"Baseline (dropped) sector: {sectors_universe[0]}\n")
    for label, recs in (("FIT", fit), ("HOLDOUT", holdout)):
        print(f"-- {label} --")
        result = sector_dummy_fm(recs, sectors_universe)
        robust = [(sec, m, t) for sec, (m, t) in result.items() if abs(t) >= 2.0]
        for sec, (m, t) in sorted(result.items(), key=lambda kv: -abs(kv[1][1])):
            flag = " <-- |t|>=2" if abs(t) >= 2.0 else ""
            print(f"    {sec:35s} mean_coef={m:9.5f}  t={t:6.2f}{flag}")
        print(f"  {len(robust)}/{len(result)} sectors clear |t|>=2 in {label}\n")


if __name__ == "__main__":
    main()
