#!/usr/bin/env python3
"""
Interaction check: does EVERY candidate ever discussed for Quality have a forward-return signal
that depends on ROA level, even ones whose pooled linear test found nothing?

Built 2026-08-26, follow-up to quality_ml_feature_importance.py's walk-forward result - that
model ranked net_margin/margin_volatility_3y #2/#3 by permutation importance despite both
failing fama_macbeth_quality_factors.py's linear multivariate test (net_margin's effect
collapses from t=2.16 univariate to t=-0.08 once ROA is controlled for, and turned out to be a
real interaction - see quality_net_margin_roa_interaction_effect_found_20260826 in MEMORY.md:
low-ROA t=+2.18, high-ROA t=-2.61, canceling out in the pooled regression). A LINEAR regression
with terms as separate additive predictors can only ever find "no effect beyond ROA" or "some
effect beyond ROA" - it structurally cannot see a CONDITIONAL effect, which is exactly the kind
of thing a tree model's importance ranking can pick up on and a linear model can't.

EXPANDED 2026-08-26 (user request) from just the 2 ML-flagged candidates to every candidate ever
discussed for this pillar (all of QUALITY_FACTOR_COLS/EXTENDED_CANDIDATE_COLS/
ROIC_CANDIDATE_COLS/NEW_CANDIDATE_COLS/CASH_QUALITY_CANDIDATE_COLS except roa itself) - net_margin
proved a real interaction was hiding behind a null pooled result, so it's worth checking whether
any of the OTHER "no independent signal" verdicts (operating_margin, current_ratio, roic_pct,
accruals_ratio, gross/operating_profitability, the cash-quality candidates, etc.) are hiding the
same thing, not just assuming net_margin was a one-off.

This does NOT refit a tree model - it's a much simpler, more interpretable test: split each
month's cross-section into ROA terciles (within that month, so no look-ahead), then run
fama_macbeth_price_factors.py's own _fama_macbeth univariate regression of each candidate on
forward return SEPARATELY within each tercile. If a candidate's t-stat is real in one tercile
and flat/opposite in another, that's a genuine interaction the pooled test missed. If it's flat
everywhere, that reconfirms the original "no independent signal" verdict.

Usage:
    python -m algo.research.quality_margin_interaction_check [options]
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import (
    CASH_QUALITY_CANDIDATE_COLS,
    EXTENDED_CANDIDATE_COLS,
    NEW_CANDIDATE_COLS,
    QUALITY_FACTOR_COLS,
    ROIC_CANDIDATE_COLS,
    build_quality_panel,
    fetch_annual_quality_fundamentals,
)

logger = logging.getLogger(__name__)

# EXPANDED 2026-08-26 (user request: "make sure those are included ... look back a bit, all the
# ones I asked you about") - every candidate ever discussed this session, not just the 2 the ML
# walk-forward happened to flag. Excludes altman_z_score (excluded on a methodological
# argument, not a stats one - see quality_altman_z_removed_distress_classifier_not_continuous_
# input_20260826 in MEMORY.md; an interaction result wouldn't change that reasoning, and its
# ~23% coverage would make already-thin tercile splits thinner still).
ALL_TESTABLE = list(
    dict.fromkeys(
        [
            *QUALITY_FACTOR_COLS,
            *EXTENDED_CANDIDATE_COLS,
            *ROIC_CANDIDATE_COLS,
            *NEW_CANDIDATE_COLS,
            *CASH_QUALITY_CANDIDATE_COLS,
        ]
    )
)


def run(start_date: str, end_date: str, min_cross_section: int, condition_on: str, candidates: list[str]) -> None:
    logger.info("Fetching annual quality fundamentals (point-in-time reconstruction)")
    fund = fetch_annual_quality_fundamentals()
    quality_panel = build_quality_panel(fund)

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    needed_cols = list(dict.fromkeys([condition_on, *candidates]))
    monthly = merge_asof_monthly(months, quality_panel, cols=needed_cols)

    # Bucket by condition_on tercile WITHIN each month (cross-sectional, no look-ahead) - a
    # firm's tercile can move month to month as its own fundamentals update or the universe
    # shifts, same point-in-time discipline as every other script in this file family.
    tercile_records: dict[str, dict[str, list[tuple[pd.Timestamp, pd.DataFrame]]]] = {
        c: {"low": [], "mid": [], "high": []} for c in candidates
    }

    for i in range(len(months) - 1):
        month = months[i]
        qframe = monthly.get(month)
        if qframe is None or qframe.empty:
            continue
        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        frame = qframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        frame = frame.dropna(subset=[condition_on])
        if len(frame) < min_cross_section:
            continue
        # FIXED 2026-08-26 (live-caught, user-prompted re-check): plain pd.qcut on the raw
        # value throws when the tercile boundary lands on a repeated value - e.g.
        # debt_to_equity has so many companies at exactly 0.0 that the 33rd percentile is
        # often 0.0 too, and the old `except ValueError: continue` was SILENTLY discarding
        # 84 of 152 months (55%) for debt_to_equity specifically, making that conditioning
        # variable look far more data-starved than it actually is (raw coverage is ~88%,
        # same ballpark as roa's ~92%). Ranking first (method="first" breaks ties by row
        # order, giving unique ranks) makes qcut always produce exactly 3 real, roughly
        # equal-sized bins regardless of how many duplicate raw values exist - the standard
        # fix for this exact pandas gotcha, not a data limitation to route around.
        frame["_tercile"] = pd.qcut(frame[condition_on].rank(method="first"), 3, labels=["low", "mid", "high"])

        for candidate in candidates:
            if candidate == condition_on:
                continue
            for tercile in ("low", "mid", "high"):
                sub = frame[frame["_tercile"] == tercile][[candidate, "fwd_ret"]].dropna()
                if len(sub) < max(30, min_cross_section // 4):
                    continue
                lo, hi = sub[candidate].quantile([0.01, 0.99])
                sub = sub.copy()
                sub[candidate] = sub[candidate].clip(lo, hi)
                std = sub[candidate].std()
                sub[candidate] = (sub[candidate] - sub[candidate].mean()) / std if std > 0 else 0.0
                tercile_records[candidate][tercile].append((month, sub))

    print(f"=== Does the candidate's signal depend on which {condition_on} tercile a stock is in? ===")
    print(f"{'candidate':22s} {'tercile':6s} {'n_months':>9s} {'mean_coef':>10s} {'t_stat':>8s}")
    for candidate in candidates:
        if candidate == condition_on:
            continue
        for tercile in ("low", "mid", "high"):
            records = tercile_records[candidate][tercile]
            if not records:
                print(f"{candidate:22s} {tercile:6s} {'(no usable months)':>9s}")
                continue
            result = _fama_macbeth(records, [candidate])
            mean, t = result[candidate]
            print(f"{candidate:22s} {tercile:6s} {len(records):9d} {mean:10.5f} {t:8.2f}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument(
        "--condition-on", default="roa", help="Column whose terciles gate the candidate test (default: roa)"
    )
    parser.add_argument(
        "--candidates",
        default=None,
        help="Comma-separated candidate columns to test (default: every candidate except --condition-on)",
    )
    args = parser.parse_args()

    candidates = (
        [c.strip() for c in args.candidates.split(",")]
        if args.candidates
        else [c for c in ALL_TESTABLE if c != args.condition_on]
    )

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.condition_on, candidates)


if __name__ == "__main__":
    main()
