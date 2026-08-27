#!/usr/bin/env python3
"""
Tests capex_intensity (Capex / Revenue) as a Growth candidate - flagged as a gap 2026-08-27
(user-supplied literature checklist). Never tested anywhere in this codebase; `capex` already
exists in annual_cash_flow (used for free_cash_flow = ocf - capex upstream), no new data source
needed. Scored as -capex_intensity (lower capital intensity = better, matching this pillar's own
asset_growth_yoy sign-flip convention for "leaner is better" style Growth/CMA-adjacent signals) -
tested both directions below so the sign isn't assumed.

Two other Growth gaps from the same checklist were checked and found genuinely UNTESTABLE, not
attempted here:
- R&D intensity / Mohanram G-Score: no research_development (or any R&D) column exists anywhere
  in annual_income_statement - checked via information_schema directly. Both R&D intensity itself
  and Mohanram G-Score (which needs R&D/advertising intensity as inputs) are blocked by this same
  missing data source, not a modeling gap.
- Analyst estimate revisions (direction/magnitude of consensus forward EPS change): the fields
  already exist (quality_metrics.estimate_revision_direction etc.) but their source table
  (analyst_earnings_estimates.forward_eps) only has 23 days of history (2026-08-03 to 08-26,
  21 distinct dates) - nowhere near enough for a real point-in-time Fama-MacBeth test. A genuine
  data-depth gap, not a "haven't built it yet" gap - revisit once real history accumulates.

Usage:
    python -m algo.research.growth_capex_intensity_candidate
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import REPORTING_LAG_DAYS, merge_asof_monthly
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

CANDIDATES = ["capex_intensity", "capex_intensity_neg"]


def fetch_capex_panel() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year, i.revenue, c.capex
        FROM annual_income_statement i
        LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["symbol", "fiscal_year", "revenue", "capex"])
    df["revenue"] = df["revenue"].astype(float)
    df["capex"] = df["capex"].astype(float)
    return df


def build_panel(fund: pd.DataFrame) -> pd.DataFrame:
    out = fund[["symbol", "fiscal_year"]].copy()
    # capex is stored as a negative cash outflow in this schema (matches free_cash_flow = ocf +
    # capex elsewhere in this codebase, i.e. capex already carries its own sign) - abs() to get
    # a positive intensity ratio.
    out["capex_intensity"] = np.where(fund["revenue"] > 0, fund["capex"].abs() / fund["revenue"], np.nan)
    out["capex_intensity_neg"] = -out["capex_intensity"]
    out["known_date"] = pd.to_datetime(out["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
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
    fund = fetch_capex_panel()
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
        if len(frame.dropna(subset=["capex_intensity"])) < min_cross_section:
            continue
        records.append((month, frame))
    return records


def run(start_date: str, end_date: str, min_cross_section: int, split_date: str) -> None:
    records = build_records(start_date, end_date, min_cross_section)
    if not records:
        raise RuntimeError("No usable cross-sectional months")

    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})\n")

    split_ts = pd.Timestamp(split_date)
    first_half = [r for r in records if pd.Timestamp(r[0]) < split_ts]
    second_half = [r for r in records if pd.Timestamp(r[0]) >= split_ts]

    for label, recs in (
        ("FULL SAMPLE", records),
        (f"FIRST HALF (< {split_date})", first_half),
        (f"SECOND HALF (>= {split_date})", second_half),
    ):
        print(f"--- {label} ({len(recs)} months) ---")
        for c in ["capex_intensity"]:
            usable = [(m, f.dropna(subset=[c])) for m, f in recs]
            usable = [(m, f) for m, f in usable if len(f) >= min_cross_section]
            if not usable:
                print(f"  {c:20s} (no usable months)")
                continue
            result = _fama_macbeth(usable, [c])
            mean, t = result[c]
            print(f"  {c:20s} mean_coef={mean:10.5f}  t_stat={t:7.2f}  n_months={len(usable):4d}")
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
