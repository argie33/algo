#!/usr/bin/env python3
"""
Tests 2 genuinely untested Growth candidates flagged from the 2026-08-27 literature checklist
follow-up: Reinvestment Rate and Book Value Growth. Neither is computed anywhere in this
codebase today. Mirrors algo/research/fama_macbeth_growth_factors.py and
growth_capex_intensity_candidate.py's conventions (point-in-time annual-statement
reconstruction, 90-day reporting lag, monthly as-of merge, full-sample + half-split at
2020-06-01, both univariate and multivariate-controlled-for-the-live-11-input-blend).

Reinvestment Rate = (Capex_abs - D&A + delta_NWC) / NOPAT
  NOPAT = operating_income * (1 - effective_tax_rate), effective_tax_rate =
  clip(income_tax_expense / pretax_income, 0, 1) (guards negative/>100% pretax-income noise,
  same defensive-clip spirit as this file family's other implausible-ratio guards).
  delta_NWC = (current_assets - current_liabilities) YoY change. D&A = depreciation_expense +
  amortization_expense (annual_income_statement, same fields CASH_QUALITY_CANDIDATE_COLS added
  for EBITDA reconstruction - see fama_macbeth_quality_factors.py). Literature (Fama-French 2015
  CMA factor, Titman/Wei/Xie 2004, Cooper/Gulen/Schill 2008 asset-growth anomaly) predicts
  aggressive reinvestment -> LOWER forward returns, i.e. a NEGATIVE coefficient is the expected
  "textbook-consistent" sign - tested both directions, not assumed.

Book Value Growth = YoY growth of stockholders_equity / shares_outstanding_diluted (falls back
to _basic, then _dei - same waterfall precedence as this repo's other per-share fields).

Usage:
    python -m algo.research.growth_reinvestment_book_value_candidates
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_growth_factors import (
    GROWTH_FACTOR_COLS,
    REPORTING_LAG_DAYS,
    build_growth_panel,
    fetch_annual_fundamentals,
    merge_asof_monthly,
)
from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

CANDIDATES = ["reinvestment_rate", "book_value_growth"]


def fetch_panel_raw() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year,
               i.operating_income, i.income_tax_expense, i.pretax_income,
               i.depreciation_expense, i.amortization_expense,
               COALESCE(i.shares_outstanding_diluted, i.shares_outstanding_basic,
                        i.shares_outstanding_dei) AS shares,
               c.capex,
               b.current_assets, b.current_liabilities, b.stockholders_equity
        FROM annual_income_statement i
        LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    cols = [
        "symbol",
        "fiscal_year",
        "operating_income",
        "income_tax_expense",
        "pretax_income",
        "depreciation_expense",
        "amortization_expense",
        "shares",
        "capex",
        "current_assets",
        "current_liabilities",
        "stockholders_equity",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in cols[2:]:
        df[c] = df[c].astype(float)
    return df


def build_panel(fund: pd.DataFrame) -> pd.DataFrame:
    fund = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    g = fund.groupby("symbol", group_keys=False)

    tax_rate = (fund["income_tax_expense"] / fund["pretax_income"]).clip(0.0, 1.0)
    tax_rate = tax_rate.where(fund["pretax_income"] > 0)
    nopat = fund["operating_income"] * (1.0 - tax_rate)
    da = fund["depreciation_expense"].fillna(0.0) + fund["amortization_expense"].fillna(0.0)
    prior_ca = g["current_assets"].shift(1)
    prior_cl = g["current_liabilities"].shift(1)
    delta_nwc = (fund["current_assets"] - prior_ca) - (fund["current_liabilities"] - prior_cl)

    out = fund[["symbol", "fiscal_year"]].copy()
    reinvestment = fund["capex"].abs() - da + delta_nwc
    out["reinvestment_rate"] = np.where(nopat > 0, reinvestment / nopat, np.nan)

    bvps = fund["stockholders_equity"] / fund["shares"]
    bvps = bvps.where((fund["shares"] > 0) & (fund["stockholders_equity"] > 0))
    prior_bvps = g["stockholders_equity"].shift(1) / g["shares"].shift(1)
    valid_bv = (prior_bvps > 0) & (bvps > 0)
    out["book_value_growth"] = np.where(valid_bv, bvps / prior_bvps - 1.0, np.nan)

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
    fund = fetch_panel_raw()
    panel = build_panel(fund)
    growth_panel = build_growth_panel(fetch_annual_fundamentals())

    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly_new = merge_asof_monthly(months, panel, cols=CANDIDATES)
    monthly_growth = merge_asof_monthly(months, growth_panel, cols=GROWTH_FACTOR_COLS)

    records = []
    for i in range(len(months) - 1):
        month = months[i]
        nframe = monthly_new.get(month)
        gframe = monthly_growth.get(month)
        if nframe is None or nframe.empty or gframe is None or gframe.empty:
            continue
        fwd_ret = px.iloc[i + 1] / px.iloc[i] - 1.0
        frame = nframe.join(gframe, how="inner").join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        for c in CANDIDATES + GROWTH_FACTOR_COLS:
            frame[c] = _zwinsor(frame[c])
        if len(frame) < min_cross_section:
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
        for c in CANDIDATES:
            uni_usable = [(m, f.dropna(subset=[c])) for m, f in recs]
            uni_usable = [(m, f) for m, f in uni_usable if len(f) >= min_cross_section]
            multi_usable = [(m, f.dropna(subset=[c, *GROWTH_FACTOR_COLS])) for m, f in recs]
            multi_usable = [(m, f) for m, f in multi_usable if len(f) >= min_cross_section]
            if not uni_usable:
                print(f"  {c:20s} (no usable months)")
                continue
            uni = _fama_macbeth(uni_usable, [c])
            mean, t = uni[c]
            if multi_usable:
                multi = _fama_macbeth(multi_usable, [c, *GROWTH_FACTOR_COLS])
                mmean, mt = multi[c]
                multi_str = f"multivariate(ctrl live-11) mean={mmean:9.5f} t={mt:7.2f} n={len(multi_usable):4d}"
            else:
                multi_str = "multivariate: no usable months"
            print(f"  {c:20s} univariate mean={mean:9.5f} t={t:7.2f} n={len(uni_usable):4d}  |  {multi_str}")
        print()

    print("Correlation with asset_growth_yoy_flipped (redundancy check vs. incumbent):")
    all_frames = pd.concat([f for _, f in records], ignore_index=True)
    for c in CANDIDATES:
        corr = all_frames[[c, "asset_growth_yoy_flipped"]].dropna().corr().iloc[0, 1]
        print(f"  {c}: r={corr:.3f}")


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
