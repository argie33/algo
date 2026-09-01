#!/usr/bin/env python3
"""
Growth pillar era-consistency test.

Built 2026-08-31 (goal: "keep working on growth score i dont understand why it flips" - user
wants a definitive answer on whether ANY candidate in/near the live 11-input GROWTH_SCORE_FIELDS
blend (loaders/load_stock_scores.py, restored to equal-weight/not-sign-flipped 2026-08-28 on
explicit user override) deserves anything other than equal weight, tested to a strict bar:
|t-stat| > 2 in BOTH a first-half and second-half era split, with a CONSISTENT sign across both
halves, under the field's natural (not sign-flipped) direction - i.e. the direction that matches
how a non-inverted equal-weighted blend actually scores it (higher field value = higher score).

This directly answers a prior (unverified - never landed to disk) claim that such a test was
already run and found zero of 13 fields cleared the bar, closest being sustainable_growth_rate,
and that book_value_growth (not currently a GROWTH_SCORE_FIELDS member) had a robust ERA-CONSISTENT
NEGATIVE relationship to forward returns under the sign-FLIPPED convention. This script actually
builds and runs that test for real - no numbers should be trusted until produced by an actual run
against the live DB.

Fields tested (11 of the claimed 13 - quarterly_growth_momentum/earnings_growth_4q_avg are
computed from quarterly data by _compute_quarterly_metrics in
load_value_quality_growth_metrics.py and have NO existing point-in-time reconstruction in this
research-script family; building one from scratch is out of scope for this pass, so they are
honestly excluded, not padded in):
  revenue_growth_1y, eps_growth_1y, revenue_growth_3y, eps_growth_3y, revenue_growth_5y,
  eps_growth_5y, net_income_growth_yoy (== ni_growth_yoy), fcf_growth_yoy   [current
  GROWTH_SCORE_FIELDS members, 8 of 11 testable]
  sustainable_growth_rate   [current GROWTH_SCORE_FIELDS member, 9th testable - built here as
  roe * (1 - payout_ratio), same definition growth_multi_input_blend_test_20260828.py uses]
  book_value_growth, asset_growth_yoy   [NOT scored - the two "computed but unscored" candidates
  the prior session's claim centered on]

Point-in-time construction reuses this repo's own established machinery verbatim, no
re-derivation: fama_macbeth_growth_factors.py (annual income/cashflow/balance-sheet panel,
90-day reporting lag, GROWTH_FACTOR_COLS), growth_reinvestment_book_value_candidates.py
(book_value_growth), fama_macbeth_quality_factors.py (roe/payout_ratio for
sustainable_growth_rate). asset_growth_yoy is fama_macbeth_growth_factors.py's own
asset_growth_yoy_flipped, un-negated back to its raw (unflipped) sign so "higher value = higher
score" is the natural-direction hypothesis being tested, consistent with every other field here.

Two conventions reported per field, both diagnostic:
  NATURAL  - raw sign, matching how a non-inverted equal-weight blend currently/would score it
             (higher growth = higher score). This is the convention the "clears the bar" verdict
             is judged against.
  FLIPPED  - sign-negated (Cooper/Gulen/Schill asset-growth-reversal convention, matching this
             file family's OLDER research-script default before the 2026-08-28 user override).
             Reported only to let book_value_growth's specific claim be checked directly; NOT
             used for the pass/fail verdict, since the live formula is NOT sign-flipped by
             explicit, standing user directive (memory:
             growth_pillar_restored_multi_input_not_inverted_user_override_20260828).

RESEARCH-ONLY: does not read or write GROWTH_SCORE_FIELDS/_score_growth or any other live scoring
code. No sign-flip / no reweighting is applied to production from this script's output alone -
per the standing rule that a broad task must not reopen an already-shipped pillar formula without
surfacing the specific proposed change to the user first.

Usage:
    python -m algo.research.growth_era_consistency_test_20260831 [options]
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
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.growth_reinvestment_book_value_candidates import build_panel as build_bv_panel
from algo.research.growth_reinvestment_book_value_candidates import fetch_panel_raw as fetch_bv_fundamentals

logger = logging.getLogger(__name__)

# Maps the field name as it's known in production (GROWTH_SCORE_FIELDS / growth_metrics) to the
# column name in this script's own point-in-time panel, where they differ.
FIELD_MAP = {
    "revenue_growth_1y": "revenue_growth_1y",
    "eps_growth_1y": "eps_growth_1y",
    "revenue_growth_3y": "revenue_growth_3y",
    "eps_growth_3y": "eps_growth_3y",
    "revenue_growth_5y": "revenue_growth_5y",
    "eps_growth_5y": "eps_growth_5y",
    "net_income_growth_yoy": "net_income_growth_yoy",
    "fcf_growth_yoy": "fcf_growth_yoy",
    "sustainable_growth_rate": "sustainable_growth_rate",
    "book_value_growth": "book_value_growth",
    "asset_growth_yoy": "asset_growth_yoy",
}
LIVE_SCORED = {
    "revenue_growth_1y",
    "eps_growth_1y",
    "revenue_growth_3y",
    "eps_growth_3y",
    "revenue_growth_5y",
    "eps_growth_5y",
    "net_income_growth_yoy",
    "fcf_growth_yoy",
    "sustainable_growth_rate",
}
NOT_TESTABLE = ["quarterly_growth_momentum", "earnings_growth_4q_avg"]


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_all_records(
    start_date: str, end_date: str, min_cross_section: int
) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    logger.info("Fetching annual growth fundamentals")
    growth_panel = build_growth_panel(fetch_annual_fundamentals())
    growth_panel = growth_panel.rename(columns={"ni_growth_yoy": "net_income_growth_yoy"})
    growth_panel["asset_growth_yoy"] = -growth_panel["asset_growth_yoy_flipped"]

    logger.info("Fetching book_value_growth fundamentals")
    bv_panel = build_bv_panel(fetch_bv_fundamentals())

    logger.info("Fetching quality fundamentals (for sustainable_growth_rate)")
    quality_fund = build_quality_panel(fetch_annual_quality_fundamentals())
    quality_fund["sustainable_growth_rate"] = np.where(
        quality_fund["payout_ratio"].notna(),
        quality_fund["roe"] * (1.0 - quality_fund["payout_ratio"].clip(0.0, 1.0)),
        np.nan,
    )

    all_cols = [
        "revenue_growth_1y",
        "eps_growth_1y",
        "revenue_growth_3y",
        "eps_growth_3y",
        "revenue_growth_5y",
        "eps_growth_5y",
        "net_income_growth_yoy",
        "fcf_growth_yoy",
        "asset_growth_yoy",
    ]

    logger.info("Fetching month-end prices")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly_growth = merge_asof_monthly(months, growth_panel, cols=all_cols)
    monthly_bv = merge_asof_monthly(months, bv_panel, cols=["book_value_growth"])
    monthly_q = merge_asof_monthly(months, quality_fund, cols=["sustainable_growth_rate"])

    records = []
    for i in range(len(months) - 1):
        month = months[i]
        gf = monthly_growth.get(month)
        bf = monthly_bv.get(month)
        qf = monthly_q.get(month)
        if gf is None or gf.empty or bf is None or bf.empty or qf is None or qf.empty:
            continue
        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        frame = gf.join(bf, how="outer").join(qf, how="outer").join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        for c in [*all_cols, "book_value_growth", "sustainable_growth_rate"]:
            frame[f"z_{c}"] = _zwinsor(frame[c])
        records.append((month, frame))
    return records


def run(start_date: str, end_date: str, min_cross_section: int, split_date: str) -> None:
    records = build_all_records(start_date, end_date, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months - check fundamentals/price coverage")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    split_ts = pd.Timestamp(split_date)
    first_half = [r for r in records if pd.Timestamp(r[0]) < split_ts]
    second_half = [r for r in records if pd.Timestamp(r[0]) >= split_ts]
    print(f"Split at {split_date}: first_half={len(first_half)} months, second_half={len(second_half)} months\n")

    print(f"Excluded (no point-in-time reconstruction available): {', '.join(NOT_TESTABLE)}\n")

    eras = {"FULL": records, "ERA1": first_half, "ERA2": second_half}

    results: dict[str, dict[str, tuple[float, float, int]]] = {}
    for field, panel_col in FIELD_MAP.items():
        z_col = f"z_{panel_col}"
        results[field] = {}
        for era_label, recs in eras.items():
            usable = [(m, f.dropna(subset=[z_col, "fwd_ret"])) for m, f in recs]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if len(usable) < 2:
                results[field][era_label] = (float("nan"), float("nan"), len(usable))
                continue
            tmp = [(m, f.rename(columns={z_col: field})) for m, f in usable]
            mean, t = _fama_macbeth(tmp, [field])[field]
            results[field][era_label] = (mean, t, len(usable))

    print("########## NATURAL sign (higher field value -> hypothesized higher forward return) ##########")
    print("This is the convention the live equal-weight, non-inverted blend actually uses.\n")
    print(f"{'field':26s} {'live?':6s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for field in FIELD_MAP:
        live = "yes" if field in LIVE_SCORED else "no"
        for era_label in eras:
            mean, t, n = results[field][era_label]
            print(f"{field:26s} {live:6s} {era_label:6s} {mean:10.5f} {t:8.2f} {n:9d}")
        print()

    print("########## Era-consistency verdict (bar: |t|>2 in BOTH ERA1 and ERA2, same sign, sign>0) ##########\n")
    cleared = []
    for field in FIELD_MAP:
        _m1, t1, _n1 = results[field]["ERA1"]
        _m2, t2, _n2 = results[field]["ERA2"]
        ok = (
            not np.isnan(t1)
            and not np.isnan(t2)
            and abs(t1) > 2
            and abs(t2) > 2
            and np.sign(t1) == np.sign(t2)
            and t1 > 0
        )
        if ok:
            cleared.append(field)
        print(f"  {field:26s} ERA1 t={t1:7.2f}  ERA2 t={t2:7.2f}  {'CLEARS BAR' if ok else ''}")
    print(f"\nFields clearing the bar: {cleared if cleared else 'NONE'}\n")

    print("########## FLIPPED sign (Cooper/Gulen/Schill convention - diagnostic only, NOT live) ##########")
    print("Reported to directly check the specific book_value_growth claim under review.\n")
    print(f"{'field':26s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for field in ["book_value_growth", "asset_growth_yoy", "sustainable_growth_rate"]:
        for era_label in eras:
            mean, t, n = results[field][era_label]
            print(f"{field:26s} {era_label:6s} {-mean:10.5f} {-t:8.2f} {n:9d}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--split-date", default="2020-06-01")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.split_date)


if __name__ == "__main__":
    main()
