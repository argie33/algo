#!/usr/bin/env python3
"""
Re-test of quarterly earnings-quality candidates + an explicit recency-weighting test.

Built 2026-08-28 (goal: user asked whether industry leaders put higher weight on more
recent periods for growth scoring, and whether quarterly_growth_momentum/
earnings_growth_4q_avg "fit" in the Growth mix).

Two things motivate a fresh script rather than reusing growth_quarterly_earnings_quality_
candidates.py (2026-08-27) as-is:

1. That script's build_panel() computed earnings_growth_4q_avg/quarterly_growth_momentum
   via SEQUENTIAL quarter-over-quarter change (s.shift(1)) - the exact seasonality bug
   just fixed in the live loader (loaders/load_value_quality_growth_metrics.py's
   _compute_quarterly_metrics(), same session). Its verdict ("clean nulls", t=-1.41/0.96)
   was measuring a seasonally-contaminated signal, not the metric's real content - stale,
   not re-usable. This script recomputes both candidates using YEAR-OVER-YEAR quarterly
   comparison (shift(4), i.e. each quarter vs the same quarter a year ago), matching the
   corrected live construction.

2. Adds a direct test of the "should recent periods get extra weight" question: a
   RECENCY-WEIGHTED variant of the live 5-input growth_equal blend that gives the
   YoY-quarterly-trend candidates (recency-tilted, updates every quarter) explicit extra
   weight over the point-in-time annual candidates (revenue_growth_1y/eps_growth_1y/
   ocf_growth_yoy/book_value_growth/sustainable_growth_rate, which only update once a
   year), tested head-to-head against the current EQUAL blend on the same panel
   methodology as growth_multi_input_blend_test_20260828.py.

Reporting lag: same 45-day 10-Q filing-lag convention as the 2026-08-27 script (SEC
deadline is 40 days for large accelerated filers, 45 for others - conservative choice to
avoid look-ahead).

Usage:
    python -m algo.research.growth_quarterly_yoy_recency_test_20260828
"""

import argparse
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_composite_weights import _zwinsor
from algo.research.fama_macbeth_growth_factors import (
    build_growth_panel,
    fetch_annual_fundamentals,
)
from algo.research.fama_macbeth_growth_factors import (
    merge_asof_monthly as merge_asof_monthly_growth,
)
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import build_quality_panel, fetch_annual_quality_fundamentals
from algo.research.growth_reinvestment_book_value_candidates import build_panel as build_book_value_panel
from algo.research.growth_reinvestment_book_value_candidates import fetch_panel_raw as fetch_book_value_fundamentals
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

QUARTERLY_CANDIDATES = ["earnings_growth_4q_avg_yoy", "quarterly_growth_momentum_yoy"]
ANNUAL_CANDIDATE_COLS = [
    "revenue_growth_1y",
    "eps_growth_1y",
    "ocf_growth_yoy",
    "book_value_growth",
    "sustainable_growth_rate",
]
QUARTER_END_MONTH_DAY = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
QUARTERLY_REPORTING_LAG_DAYS = 45


def fetch_quarterly_panel() -> pd.DataFrame:
    sql = """
        SELECT symbol, fiscal_year, fiscal_quarter, net_income, revenue, COALESCE(eps, earnings_per_share) AS eps
        FROM quarterly_income_statement
        WHERE fiscal_year BETWEEN 2000 AND 2026 AND fiscal_quarter BETWEEN 1 AND 4
          AND COALESCE(data_unavailable, false) = false
        ORDER BY symbol, fiscal_year, fiscal_quarter
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "fiscal_year", "fiscal_quarter", "net_income", "revenue", "eps"])
    for c in ["net_income", "revenue", "eps"]:
        df[c] = df[c].astype(float)
    return df


def _quarter_end_date(row: pd.Series) -> pd.Timestamp:
    month, day = QUARTER_END_MONTH_DAY[int(row["fiscal_quarter"])]
    return pd.Timestamp(year=int(row["fiscal_year"]), month=month, day=day)


def build_quarterly_yoy_panel(fund: pd.DataFrame) -> pd.DataFrame:
    """YoY version: each quarter compared to the SAME quarter 4 rows back (one year prior),
    not the immediately preceding quarter. Assumes no gaps in a symbol's quarterly filing
    sequence (a simplification shared with the sequential-QoQ predecessor script and the
    live loader's own index-offset predecessor) - a real limitation but the same one this
    repo has always accepted for this table, not new here.
    """
    fund = fund.sort_values(["symbol", "fiscal_year", "fiscal_quarter"]).reset_index(drop=True)
    fund["quarter_end"] = fund.apply(_quarter_end_date, axis=1)
    fund["known_date"] = fund["quarter_end"] + pd.Timedelta(days=QUARTERLY_REPORTING_LAG_DAYS)

    g = fund.groupby("symbol", group_keys=False)

    eps_yoy = g["eps"].transform(lambda s: (s - s.shift(4)) / s.shift(4).abs() * 100.0)
    eps_yoy = eps_yoy.where(fund["eps"].notna() & g["eps"].shift(4).notna() & (g["eps"].shift(4) != 0))
    rev_yoy = g["revenue"].transform(lambda s: (s - s.shift(4)) / s.shift(4).abs() * 100.0)
    rev_yoy = rev_yoy.where(fund["revenue"].notna() & g["revenue"].shift(4).notna() & (g["revenue"].shift(4) != 0))

    fund["_eps_yoy"] = eps_yoy
    fund["_rev_yoy"] = rev_yoy
    # Trailing-4-quarter average of the last 4 YoY comparisons (mirrors the live loader's
    # "average of whichever of the last 4 quarters has a same-quarter-prior-year match").
    fund["earnings_growth_4q_avg_yoy"] = g["_eps_yoy"].rolling(4, min_periods=1).mean().reset_index(level=0, drop=True)
    fund["quarterly_growth_momentum_yoy"] = (
        g["_rev_yoy"].rolling(4, min_periods=1).mean().reset_index(level=0, drop=True)
    )

    for c in QUARTERLY_CANDIDATES:
        fund[c] = fund[c].where(fund[c].abs() < 100000)

    out = fund[["symbol", "fiscal_year", "fiscal_quarter", "known_date", *QUARTERLY_CANDIDATES]].copy()
    return out.dropna(subset=["known_date"])


def _renormalized_blend(z: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    w = pd.Series(weights)
    avail = z.notna()
    w_matrix = avail.mul(w, axis=1)
    row_weight_sum = w_matrix.sum(axis=1)
    weighted = (z.fillna(0.0) * w_matrix).sum(axis=1)
    out = pd.Series(np.nan, index=z.index)
    valid = row_weight_sum > 0
    out.loc[valid] = weighted.loc[valid] / row_weight_sum.loc[valid]
    return out


def _ic_mean_t(ics: np.ndarray[Any, Any]) -> tuple[float, float, int]:
    if len(ics) < 2:
        return (float("nan"), float("nan"), len(ics))
    se = ics.std(ddof=1) / np.sqrt(len(ics))
    t = ics.mean() / se if se > 0 else float("nan")
    return (ics.mean(), t, len(ics))


def _spearman_ic_series(recs: list[tuple[pd.Timestamp, pd.DataFrame]], col: str) -> np.ndarray[Any, Any]:
    ics = []
    for _m, f in recs:
        if len(f) < 10:
            continue
        ic = f[col].corr(f["fwd_ret"], method="spearman")
        if ic is not None and not np.isnan(ic):
            ics.append(ic)
    return np.array(ics)


def run(start_date: str, end_date: str, min_cross_section: int) -> None:
    logger.info("Fetching quarterly panel + annual growth/quality/book-value panels")
    q_fund = fetch_quarterly_panel()
    q_panel = build_quarterly_yoy_panel(q_fund)

    growth_raw = fetch_annual_fundamentals()
    growth_panel = build_growth_panel(growth_raw)
    bv_panel = build_book_value_panel(fetch_book_value_fundamentals())
    quality_raw = fetch_annual_quality_fundamentals()
    quality_fund = build_quality_panel(quality_raw)
    quality_fund["sustainable_growth_rate"] = np.where(
        quality_fund["payout_ratio"].notna(),
        quality_fund["roe"] * (1.0 - quality_fund["payout_ratio"].clip(0.0, 1.0)),
        np.nan,
    )

    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    q_monthly = merge_asof_monthly_growth(months, q_panel, cols=QUARTERLY_CANDIDATES)
    growth_monthly = merge_asof_monthly_growth(
        months, growth_panel, cols=["revenue_growth_1y", "eps_growth_1y", "ocf_growth_yoy"]
    )
    bv_monthly = merge_asof_monthly_growth(months, bv_panel, cols=["book_value_growth"])
    quality_monthly = merge_asof_monthly_growth(months, quality_fund, cols=["sustainable_growth_rate"])

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - 1):
        month = months[i]
        qf = q_monthly.get(month)
        gr = growth_monthly.get(month)
        bv = bv_monthly.get(month)
        qual = quality_monthly.get(month)
        if qf is None or gr is None or bv is None or qual is None:
            continue
        if qf.empty or gr.empty or bv.empty or qual.empty:
            continue

        idx = qf.index.union(gr.index).union(bv.index).union(qual.index)
        cand = pd.DataFrame(index=idx)
        cand["earnings_growth_4q_avg_yoy"] = qf["earnings_growth_4q_avg_yoy"].reindex(idx)
        cand["quarterly_growth_momentum_yoy"] = qf["quarterly_growth_momentum_yoy"].reindex(idx)
        cand["revenue_growth_1y"] = gr["revenue_growth_1y"].reindex(idx)
        cand["eps_growth_1y"] = gr["eps_growth_1y"].reindex(idx)
        cand["ocf_growth_yoy"] = gr["ocf_growth_yoy"].reindex(idx)
        cand["book_value_growth"] = bv["book_value_growth"].reindex(idx)
        cand["sustainable_growth_rate"] = qual["sustainable_growth_rate"].reindex(idx)

        # Sign-flip convention matches _score_growth's live docstring (Cooper/Gulen/Schill
        # reversal - lower growth scores higher). Winsorize+z-score each independently.
        z = pd.DataFrame(index=idx)
        for col in [*QUARTERLY_CANDIDATES, *ANNUAL_CANDIDATE_COLS]:
            z[col] = -_zwinsor(cand[col])

        growth_equal_5 = _renormalized_blend(z[ANNUAL_CANDIDATE_COLS], dict.fromkeys(ANNUAL_CANDIDATE_COLS, 1.0))
        # RECENCY-WEIGHTED: same 5 annual inputs at their current equal weight (1.0 each,
        # summing to 5), PLUS the 2 quarterly YoY-trend candidates each given 2x an
        # individual annual input's weight (2.0 each) - the quarterly candidates update
        # 4x/year vs the annual candidates' 1x/year, so this deliberately overweights the
        # more-frequently-refreshed signal, mirroring IBD's C (current quarter) > A (annual)
        # emphasis without discarding the annual inputs entirely.
        recency_weights = {**dict.fromkeys(ANNUAL_CANDIDATE_COLS, 1.0), **dict.fromkeys(QUARTERLY_CANDIDATES, 2.0)}
        growth_recency = _renormalized_blend(z, recency_weights)

        fwd_ret = px.iloc[i + 1].reindex(idx) / px.iloc[i].reindex(idx) - 1.0

        frame = pd.DataFrame(
            {
                "earnings_growth_4q_avg_yoy": z["earnings_growth_4q_avg_yoy"],
                "quarterly_growth_momentum_yoy": z["quarterly_growth_momentum_yoy"],
                "growth_equal_5": growth_equal_5,
                "growth_recency": growth_recency,
                "fwd_ret": fwd_ret,
            }
        )
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    sizes = [len(f) for _, f in records]
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    split_idx = len(records) // 2
    halves = {"FULL": records, "ERA1": records[:split_idx], "ERA2": records[split_idx:]}

    print("########## Isolated univariate Fama-MacBeth: YoY quarterly candidates ##########\n")
    print(f"{'candidate':28s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for cand in QUARTERLY_CANDIDATES:
        for era_label, era_records in halves.items():
            usable = [(m, f.dropna(subset=[cand, "fwd_ret"])) for m, f in era_records]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if not usable:
                print(f"{cand:28s} {era_label:6s} {'(no usable months)':>10s}")
                continue
            mean, t = _fama_macbeth(usable, [cand])[cand]
            print(f"{cand:28s} {era_label:6s} {mean:10.5f} {t:8.2f} {len(usable):9d}")
        print()

    print("########## Coverage: % of universe with a real value ##########\n")
    for cand in [*QUARTERLY_CANDIDATES, "growth_equal_5", "growth_recency"]:
        cov = np.mean([f[cand].notna().mean() for _, f in records])
        print(f"  {cand:28s} {cov * 100:6.1f}%")
    print()

    print("########## EQUAL(5) vs RECENCY-WEIGHTED(5+2 quarterly) blend, univariate FM ##########\n")
    print(f"{'variant':16s} {'era':6s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    for variant in ["growth_equal_5", "growth_recency"]:
        for era_label, era_records in halves.items():
            usable = [(m, f.dropna(subset=[variant, "fwd_ret"])) for m, f in era_records]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if not usable:
                continue
            mean, t = _fama_macbeth(usable, [variant])[variant]
            print(f"{variant:16s} {era_label:6s} {mean:10.5f} {t:8.2f} {len(usable):9d}")
        print()

    print("########## Stability check: per-half-era IC swing (mean IC, era1 vs era2) ##########\n")
    print(f"{'variant':28s} {'era1_ic':>9s} {'era2_ic':>9s} {'abs_swing':>10s}")
    for variant in [*QUARTERLY_CANDIDATES, "growth_equal_5", "growth_recency"]:
        ic1 = _spearman_ic_series(halves["ERA1"], variant)
        ic2 = _spearman_ic_series(halves["ERA2"], variant)
        m1, _t1, _n1 = _ic_mean_t(ic1)
        m2, _t2, _n2 = _ic_mean_t(ic2)
        print(f"{variant:28s} {m1:9.4f} {m2:9.4f} {abs(m1 - m2):10.4f}")
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
