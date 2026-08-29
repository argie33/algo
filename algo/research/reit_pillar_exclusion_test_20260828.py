#!/usr/bin/env python3
"""
REIT pillar-exclusion test - does GOVERNANCE.md's own established playbook fix Real Estate's
Growth/Quality breakdown, without building new REIT-specific infrastructure?

Built 2026-08-28. Two prior findings this session found Real Estate specifically has broken
fundamentals-pillar signal: [[sector_relative_value_scoring_tested_mixed_not_shipped_20260828]]
(Quality's IC ~0/not significant for Real Estate) and
[[growth_multi_input_blend_tested_not_robust_reit_signal_backwards_20260828]] (Growth's IC is
SIGNIFICANTLY NEGATIVE for Real Estate, t=-2.11). User pushback on building brand-new REIT-specific
infrastructure (FFO/AFFO - confirmed via repo-wide grep this session: NOT currently ingested
anywhere, a real new-data-source project, not a quick formula tweak) - "maybe we need to review
further" whether something simpler already covers this. GOVERNANCE.md's own Data Quality section
literally already names this exact scenario: "When seeing data_unavailable=TRUE markers appearing
for a new class of symbols (REITs, micro-caps, foreign stocks, etc.) ... Add explicit data quality
gate ('skip REITs with <3 years SEC data'), then ALLOW the data_unavailable marker" - i.e. this
project's own established playbook is to EXCLUDE a pillar for a class of symbols it doesn't apply
to (marking data_unavailable, letting the composite renormalize over the remaining pillars - the
exact mechanism `_compute_stock_score` already uses for any ordinary missing-data case), not to
build new sector-specific formulas. This script tests whether that already-established mechanism
would actually help for Real Estate specifically, before treating "build FFO-based scoring" as the
only path.

Method: reuses cross_pillar_interaction_sweep_20260828.py's already-built complete-case panel
(all 6 pillar proxies, current live formulas) + sector_relative_scoring_test_20260828.py's sector
map. For Real Estate rows only, compares Spearman IC of:
  (a) FULL: simple average of all 6 z-scored pillar proxies (equal-weight stand-in for the live
      composite - the live BASE_PILLAR_WEIGHTS ratio isn't material to this specific comparison,
      which is about whether EXCLUDING two pillars helps, not about the exact weight numbers)
  (b) NO_GROWTH_QUALITY: average of the remaining 4 proxies only (value/stability/momentum/size)
  (c) NO_GROWTH_ONLY: average of the remaining 5 (drop Growth, keep Quality - Quality's problem
      was "not significant", not backwards, so dropping it alone may be overkill)
against forward returns, Real Estate rows only, full-sample + half-split.

Usage:
    python -m algo.research.reit_pillar_exclusion_test_20260828 [options]
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.cross_pillar_interaction_sweep_20260828 import PILLAR_COLS, build_complete_case_records
from algo.research.sector_relative_scoring_test_20260828 import fetch_sector_map

logger = logging.getLogger(__name__)

MIN_SECTOR_SLICE = 10


def _spearman_ic_series(
    records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str
) -> tuple[np.ndarray[Any, np.dtype[np.float64]], list[int]]:
    ics, ns = [], []
    for _month, frame in records:
        if len(frame) < MIN_SECTOR_SLICE:
            continue
        ic = frame[col].corr(frame["fwd_ret"], method="spearman")
        if ic is not None and not np.isnan(ic):
            ics.append(ic)
            ns.append(len(frame))
    return np.array(ics), ns


def _ic_mean_t(ics: np.ndarray[Any, np.dtype[np.float64]]) -> tuple[float, float, int]:
    if len(ics) < 2:
        return (float("nan"), float("nan"), len(ics))
    se = ics.std(ddof=1) / np.sqrt(len(ics))
    t = ics.mean() / se if se > 0 else float("nan")
    return (ics.mean(), t, len(ics))


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    records = build_complete_case_records(start_date, end_date, min_cross_section)
    sector_map = fetch_sector_map()

    no_growth_quality_cols = [c for c in PILLAR_COLS if c not in ("growth_proxy", "quality_proxy")]
    no_growth_cols = [c for c in PILLAR_COLS if c != "growth_proxy"]

    tagged: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for month, frame in records:
        frame = frame.copy()
        frame["sector"] = sector_map.reindex(frame.index)
        frame["composite_full"] = frame[PILLAR_COLS].mean(axis=1)
        frame["composite_no_growth_quality"] = frame[no_growth_quality_cols].mean(axis=1)
        frame["composite_no_growth"] = frame[no_growth_cols].mean(axis=1)
        tagged.append((month, frame))

    slices = {
        "Real Estate": [(m, f[f["sector"] == "Real Estate"]) for m, f in tagged],
        "Financial Services": [(m, f[f["sector"] == "Financial Services"]) for m, f in tagged],
        "Everyone else": [(m, f[~f["sector"].isin(["Real Estate", "Financial Services"])]) for m, f in tagged],
    }

    variants = ["composite_full", "composite_no_growth_quality", "composite_no_growth"]
    print(f"{'sector':20s} {'variant':28s} {'mean_ic':>9s} {'t_stat':>8s} {'n_months':>9s}")
    for sector_label, sliced in slices.items():
        sliced = [(m, f) for m, f in sliced if len(f) >= MIN_SECTOR_SLICE]
        for variant in variants:
            ics, _ns = _spearman_ic_series(sliced, variant)
            mean_ic, t, n = _ic_mean_t(ics)
            print(f"{sector_label:20s} {variant:28s} {mean_ic:9.4f} {t:8.2f} {n:9d}")
        print()


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
