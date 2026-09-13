#!/usr/bin/env python3
"""Research-only, one-off: extends quality_floor_vs_continuous_zscore_test_20260913.py's ROA
finding to the other floor-to-0-if-negative Quality components that have a fundamentals panel
available (roce, fcf_margin, debt_to_equity, gross_profitability - asset_turnover/margin_volatility
are not in fama_macbeth_quality_factors.py's panel and are skipped here).

Purpose: production (vqg_quality_batch.py) floors ALL 6 non-negative-domain components to 0.0 if
raw value < 0, a pattern originally motivated by ROE's specific sign-flip distress artifact and
then applied uniformly to the other 5 without independently verifying each needed it. The ROA
finding (quality_roa_floor_vs_continuous_zscore_corroborated_20260912 in memory) showed the floor
destroys real information for ROA specifically. This script checks whether the same gap
replicates for roce/fcf_margin/debt_to_equity/gross_profitability, per that memory's own
prescribed follow-up ("check whether the same floor-vs-continuous gap replicates for the other 5
floored-if-negative components... worth checking each").

debt_to_equity is directionally inverted (lower is better) - tested on the NEGATED raw value,
matching production's own convention, so a negative raw d2e (negative book equity distress)
becomes a positive negated value < 0 after negation... actually: negate first (so higher score
= better = less debt), then floor at 0 the SAME way as every other metric (negated value < 0 means
original d2e was positive/high, i.e. NOT a floor case in production's actual code - re-verify
against vqg_quality_batch.py's _negated_nonneg_raw before trusting this file's d2e numbers blindly).

Not wired into any test suite or production path - throwaway research script, scratch/ per this
repo's own convention (see CLAUDE.md's monthly-cleanup section).
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

# (panel_col, negate_before_test) - negate=True mirrors production's "lower is better" convention
COMPONENTS = [
    ("roa", False),
    ("roce", False),
    ("fcf_margin", False),
    ("debt_to_equity", True),
    ("gross_profitability", False),
]


def fetch_sector_map() -> dict[str, str]:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT symbol, sector FROM company_profile WHERE sector IS NOT NULL")
        return {row[0]: apply_mortgage_reit_sector_override(row[0], row[1]) or row[1] for row in cur.fetchall()}


def build_records(months, px, panel, sector_map, col, negate, horizon_months=1, min_cross_section=100):
    monthly = merge_asof_monthly(months, panel, cols=[col])
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
        raw = {s: float(frame.loc[s, col]) for s in symbols}
        if negate:
            raw = {s: -v for s, v in raw.items()}

        nonneg = {s: v for s, v in raw.items() if v >= 0.0}
        floor_pct = zscore_to_percentile_scale(sector_neutral_zscore(nonneg, sectors))
        frame["floor_then_zscore"] = [floor_pct.get(s, 0.0) if raw[s] >= 0 else 0.0 for s in symbols]

        continuous_pct = zscore_to_percentile_scale(sector_neutral_zscore(raw, sectors))
        frame["continuous_zscore"] = [continuous_pct.get(s, 50.0) for s in symbols]

        for c in ("floor_then_zscore", "continuous_zscore"):
            m, s = frame[c].mean(), frame[c].std()
            frame[c] = (frame[c] - m) / s if s > 0 else 0.0

        records.append((month, frame))
    return records


def split_records(records, cutoff):
    fit = [(m, f) for m, f in records if pd.Timestamp(m) < pd.Timestamp(cutoff)]
    holdout = [(m, f) for m, f in records if pd.Timestamp(m) >= pd.Timestamp(cutoff)]
    return fit, holdout


def four_block(records):
    if not records:
        return []  # research-only helper, empty input is a valid "no data" case, not an error
    months_sorted = sorted(records, key=lambda r: r[0])
    n = len(months_sorted)
    quarter = max(1, n // 4)
    blocks = [months_sorted[i : i + quarter] for i in range(0, n, quarter)]
    return blocks[:4] if len(blocks) >= 4 else blocks


def main():
    print_survivorship_bias_caveat()
    fund = fetch_annual_quality_fundamentals()
    sector_map = fetch_sector_map()
    price_df = fetch_month_end_prices("2014-01-01", "2026-09-01")
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    for col, negate in COMPONENTS:
        print(f"\n{'=' * 70}\n{col} (negate={negate})\n{'=' * 70}")
        panel = build_quality_panel(fund)[["symbol", "fiscal_year", col, "known_date"]].dropna(subset=[col])
        records = build_records(months, px, panel, sector_map, col, negate)
        if len(records) < 20:
            print(f"  SKIP - only {len(records)} usable cross-sectional months")
            continue
        fit, holdout = split_records(records, "2022-01-01")
        print(f"  months: {len(records)} total, {len(fit)} fit / {len(holdout)} holdout")

        for label, recs in (("FIT", fit), ("HOLDOUT", holdout), ("FULL", records)):
            _, t_f = _fama_macbeth(recs, ["floor_then_zscore"])["floor_then_zscore"]
            _, t_c = _fama_macbeth(recs, ["continuous_zscore"])["continuous_zscore"]
            print(f"  {label:8s}  floor t={t_f:6.2f}   continuous t={t_c:6.2f}")

        multi = _fama_macbeth(records, ["floor_then_zscore", "continuous_zscore"])
        print("  multivariate (both jointly):")
        for name, (_, t) in multi.items():
            print(f"    {name:20s} t={t:6.2f}")

        blocks = four_block(records)
        if len(blocks) == 4:
            print("  4-block era robustness (floor / continuous t-stats):")
            for i, block in enumerate(blocks):
                _, t_f = _fama_macbeth(block, ["floor_then_zscore"])["floor_then_zscore"]
                _, t_c = _fama_macbeth(block, ["continuous_zscore"])["continuous_zscore"]
                print(
                    f"    block {i + 1} ({block[0][0]} to {block[-1][0]}): floor t={t_f:6.2f}  continuous t={t_c:6.2f}"
                )


if __name__ == "__main__":
    main()
