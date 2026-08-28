#!/usr/bin/env python3
"""
Tests 2 Quality candidates flagged 2026-08-27 (goal-mode data-coverage session, same audit that
found Growth's quarterly earnings-quality gaps) - both have real computed data in quality_metrics
but had NEVER appeared in any research script (checked via `grep -rl` across algo/research/*.py):

- ebitda_margin: (operating_income + D&A) / revenue - a standard profitability ratio, distinct
  from fcf_margin (already live, FCF/revenue - nets out capex) and gross_profitability (already
  live, (Revenue-COGS)/Assets - asset-scaled, not revenue-scaled). 83.5% live coverage.
- ocf_to_net_income: operating_cash_flow / net_income - a cash-conversion "quality of earnings"
  ratio, close cousin of fcf_to_net_income (already tested via CASH_QUALITY_CANDIDATE_COLS in
  fama_macbeth_quality_factors.py, t=0.83/1.43/0.01, rejected) but NOT itself tested - OCF is
  pre-capex, FCF is post-capex, genuinely distinct enough to check independently rather than
  assume the same null. 97.9% live coverage - one of the best-covered untested fields in this
  pillar.

A third candidate considered and DROPPED before building: quick_ratio ((current_assets -
inventory)/current_liabilities) - inventory isn't fetched by fetch_annual_quality_fundamentals()
and current_ratio (same current_assets/current_liabilities components, no inventory adjustment)
already tested null (t=-0.30/0.32, sign-flips across halves) - a stricter cousin of an already-
clean-null ratio, lower priority than the two above, not built this pass.

Reuses fama_macbeth_quality_factors.py's fetch_annual_quality_fundamentals() (already has
operating_income/depreciation_expense/amortization_expense/revenue/operating_cash_flow/net_income
- no new SQL needed) rather than re-deriving fundamentals a second time.

Usage:
    python -m algo.research.quality_ebitda_margin_ocf_conversion_candidates
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import REPORTING_LAG_DAYS, merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from algo.research.fama_macbeth_quality_factors import fetch_annual_quality_fundamentals

logger = logging.getLogger(__name__)

CANDIDATES = ["ebitda_margin", "ocf_to_net_income", "gross_margin"]


def build_panel(fund: pd.DataFrame) -> pd.DataFrame:
    out = fund[["symbol", "fiscal_year"]].copy()
    da = fund["depreciation_expense"].fillna(0.0) + fund["amortization_expense"].fillna(0.0)
    da_reported = fund["depreciation_expense"].notna() & fund["amortization_expense"].notna()
    ebitda = fund["operating_income"] + da
    # Same D&A-coverage discipline as fama_macbeth_quality_factors.py's net_debt_to_ebitda
    # (isolated re-test 2026-08-27 fixed a COALESCE(D&A,0) zero-fill bug there) - only build
    # EBITDA where both D&A fields are genuinely reported, NaN otherwise, not silently zero-filled.
    out["ebitda_margin"] = np.where(da_reported & (fund["revenue"] > 0), ebitda / fund["revenue"], np.nan)
    out["ocf_to_net_income"] = np.where(
        fund["net_income"] > 0, fund["operating_cash_flow"] / fund["net_income"], np.nan
    )
    # ADDED 2026-08-28 (goal-mode session, hook pushback on "was this removal ever evidence-
    # tested?"): gross_margin (Revenue-COGS)/Revenue was removed from scoring 2026-08-11
    # (commit e38a6667d, "User-directed: current ratio, quick ratio, and gross margin (plus its
    # trend) don't belong in our factor scores") - a scope decision, NOT an FM test. Distinct
    # from the already-shipped gross_profitability (Novy-Marx (Revenue-COGS)/Assets, t=3.25/
    # 3.93/1.11) - same numerator, different denominator (margin vs. asset-efficiency framing),
    # genuinely a different economic claim, not assumed identical. Reuses the same
    # cost_of_revenue source gross_profitability already uses (69.1% coverage, same REIT/bank/
    # service-filer non-disclosure pattern already documented as genuine, not a loader bug).
    out["gross_margin"] = np.where(
        fund["revenue"] > 0, (fund["revenue"] - fund["cost_of_revenue"]) / fund["revenue"], np.nan
    )
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def _zwinsor(s: pd.Series) -> pd.Series:
    s = s.replace([np.inf, -np.inf], np.nan)
    lo, hi = s.quantile([0.01, 0.99])
    s = s.clip(lo, hi)
    std = s.std()
    return (s - s.mean()) / std if std and std > 0 else s * 0.0


def build_records(start_date: str, end_date: str, min_cross_section: int) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    fund = fetch_annual_quality_fundamentals()
    panel = build_panel(fund)

    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly = merge_asof_monthly(months, panel, cols=CANDIDATES)

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
        for c in CANDIDATES:
            frame[c] = _zwinsor(frame[c])
        records.append((month, frame))
    return records


def run(start_date: str, end_date: str, min_cross_section: int, split_date: str) -> None:
    records = build_records(start_date, end_date, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    split_ts = pd.Timestamp(split_date)
    first_half = [r for r in records if pd.Timestamp(r[0]) < split_ts]
    second_half = [r for r in records if pd.Timestamp(r[0]) >= split_ts]

    for label, recs in (
        ("FULL SAMPLE", records),
        (f"FIRST HALF (< {split_date})", first_half),
        (f"SECOND HALF (>= {split_date})", second_half),
    ):
        print(f"--- {label} ({len(recs)} months) ---")
        for c in CANDIDATES:
            usable = [(m, f.dropna(subset=[c])) for m, f in recs]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if not usable:
                print(f"  {c:20s} (no usable months)")
                continue
            avg_n = int(np.mean([len(f) for _, f in usable]))
            result = _fama_macbeth(usable, [c])
            mean, t = result[c]
            print(f"  {c:20s} mean_coef={mean:10.5f}  t_stat={t:7.2f}  n_months={len(usable):4d}  avg_n={avg_n:5d}")
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
