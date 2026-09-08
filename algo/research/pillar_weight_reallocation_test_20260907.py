#!/usr/bin/env python3
"""
Tests whether shifting BASE_PILLAR_WEIGHTS away from Value/Risk and toward Growth/Quality
improves forward-return predictive power, using the same TRUE fit(2017-2021)/holdout(2022-2026)
discipline this project's weight-revision governance policy requires (pillar_weights.py, commit
`8b42ca1ad`) before any weight change is considered.

Built 2026-09-07 (/goal session: "I know 500 S&P companies that are amazing... none of them
are near the top"). Root-caused: within the S&P 500 alone, Technology has the HIGHEST average
quality_score (66.6) and growth_score (67.1) of any sector, but the WORST average value_score
(31.3) and second-worst risk_score (42.4) - live-verified via a direct DB query grouping
stock_scores by company_profile.sector, restricted to stock_symbols.is_sp500=true. Since
BASE_PILLAR_WEIGHTS gives value=.27+risk=.19=.46 vs growth=.24+quality=.20=.44 (Value/Risk
combined slightly OUTWEIGHS Growth/Quality combined), Technology's composite_score nets out to
the WORST average of any S&P 500 sector (51.5) despite being the best on the two pillars that
most closely match what a person means by "quality/growth companies" - Value's structural
penalty against expensive-but-great businesses is not offset.

This does NOT re-litigate barra_style_neutralized_composite_20260907.py (RANKING METHOD:
universe-wide vs sector-neutral vs Barra-residual, already tested and rejected) - this tests a
different, orthogonal question: PILLAR WEIGHTS, holding the universe-wide ranking method fixed.

Usage:
    python -m algo.research.pillar_weight_reallocation_test_20260907
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import (
    PILLAR_COLS,
    PILLAR_TO_LIVE_KEY,
    _zwinsor,
    build_pillar_proxy_records,
)
from loaders.stock_scores.pillar_weights import BASE_PILLAR_WEIGHTS

logger = logging.getLogger(__name__)

# Candidate weight schemes to test against the live BASE_PILLAR_WEIGHTS, all summing to 1.0.
# "tilted": shifts 10pts total from Value+Risk (owns .46 combined) to Growth+Quality (owns .44
# combined), reversing which side of that split is larger, while leaving Momentum untouched.
# "tilted_mild": half that shift, to see if the effect is monotonic or a cliff.
CANDIDATE_WEIGHTS = {
    "live_current": dict(BASE_PILLAR_WEIGHTS),
    "tilted_mild": {"quality": 0.23, "growth": 0.27, "value": 0.23, "risk": 0.17, "momentum": 0.10},
    "tilted_full": {"quality": 0.26, "growth": 0.30, "value": 0.19, "risk": 0.15, "momentum": 0.10},
}
for name, w in CANDIDATE_WEIGHTS.items():
    total = sum(w.values())
    assert abs(total - 1.0) < 1e-9, f"{name} weights sum to {total}, not 1.0"


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Building base pillar-proxy panel (growth/value/quality/risk/momentum)")
    _rp, _rc, records_raw = build_pillar_proxy_records(start_date, end_date, min_cross_section)

    merged: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for month_raw, raw in records_raw:
        month = pd.Timestamp(month_raw)
        df = raw.copy()
        df = df.dropna(subset=["fwd_ret", *PILLAR_COLS])
        if len(df) < min_cross_section:
            continue
        for col in PILLAR_COLS:
            df[col] = _zwinsor(df[col])
        for name, weights in CANDIDATE_WEIGHTS.items():
            live_weight_map = {c: weights[PILLAR_TO_LIVE_KEY[c]] for c in PILLAR_COLS}
            df[f"composite_{name}"] = sum(df[c] * w for c, w in live_weight_map.items())
        merged.append((month, df))

    if not merged:
        raise RuntimeError("No usable months after merge - check date range / min_cross_section")

    logger.info(f"{len(merged)} usable months: {merged[0][0]} to {merged[-1][0]}")

    def _ic_series(records: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> list[float]:
        out = []
        for _m, f in records:
            g = f.dropna(subset=[col, "fwd_ret"])
            if len(g) < 20:
                continue
            out.append(g[col].corr(g["fwd_ret"], method="spearman"))
        return [c for c in out if not np.isnan(c)]

    def _report(label: str, corrs: list[float]) -> None:
        arr = np.array(corrs)
        if len(arr) == 0:
            print(f"  {label:20s}  no usable months")
            return
        mean = arr.mean()
        se = arr.std(ddof=1) / np.sqrt(len(arr)) if len(arr) > 1 else float("nan")
        t = mean / se if se and se > 0 else float("nan")
        print(f"  {label:20s}  mean_IC={mean:8.4f}  t={t:7.2f}  n_months={len(arr):4d}")

    cols = [f"composite_{name}" for name in CANDIDATE_WEIGHTS]

    fit_period = [(m, f) for m, f in merged if m.year <= 2021]
    holdout_period = [(m, f) for m, f in merged if m.year >= 2022]

    print(f"\n########## FULL SAMPLE ({merged[0][0]} to {merged[-1][0]}, {len(merged)} months) ##########")
    for c in cols:
        _report(c, _ic_series(merged, c))

    print(f"\n########## FIT PERIOD 2017-2021 ({len(fit_period)} months) ##########")
    for c in cols:
        _report(c, _ic_series(fit_period, c))

    print(f"\n########## TRUE HOLDOUT 2022-2026 ({len(holdout_period)} months) - NEVER touched above ##########")
    for c in cols:
        _report(c, _ic_series(holdout_period, c))

    print("\n=== Technology sector average composite_score, last month, per weight scheme ===")
    last_month, last_frame = merged[-1]
    print(f"({last_month})")
    from algo.research.barra_style_neutralized_composite_20260907 import fetch_symbol_industry_and_sector

    prof = fetch_symbol_industry_and_sector()
    tech_symbols = prof.index[prof["sector"] == "Technology"]
    for c in cols:
        f = last_frame.dropna(subset=[c])
        tech_avg = f.loc[f.index.intersection(tech_symbols), c].mean()
        overall_avg = f[c].mean()
        print(f"  {c:20s}  tech_avg_z={tech_avg:7.3f}  overall_avg_z={overall_avg:7.3f}")


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
