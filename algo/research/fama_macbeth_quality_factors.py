#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for the Quality pillar's base score.

Built 2026-08-25 (goal: re-audit ALL stock_scores inputs without bias toward what already
shipped). Tests the actual upstream quality_score formula (load_value_quality_growth_metrics.py,
~line 3313-3330: simple equal-weighted average of roe/roa/operating_margin/net_margin/
debt_to_assets/interest_coverage - see the corrected docstring on StockScoresLoader._score_quality
in loaders/load_stock_scores.py for why the previously-documented "Margins 30% + Profitability
25% + Leverage 25% + Growth 20%" weighting was stale/wrong) using a point-in-time panel
reconstructed the same way as fama_macbeth_growth_factors.py/fama_macbeth_value_factors.py -
same calendar-FYE + 90-day-lag caveat applies.

Ratio definitions (matching the upstream loader's own conventions):
- roe = net_income / stockholders_equity
- roa = net_income / total_assets
- operating_margin = operating_income / revenue
- net_margin = net_income / revenue
- debt_to_assets = (long_term_debt + short_term_debt) / total_assets
- interest_coverage = operating_income / interest_expense (EBIT proxy over interest expense)

Usage:
    python -m algo.research.fama_macbeth_quality_factors [options]
    (same --start-date/--end-date/--min-cross-section/--horizon-months args as the other harnesses)
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

QUALITY_FACTOR_COLS = ["roe", "roa", "operating_margin", "net_margin", "debt_to_assets", "interest_coverage"]


def fetch_annual_quality_fundamentals() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year,
               i.revenue, i.operating_income, i.net_income, i.interest_expense,
               b.stockholders_equity, b.total_assets, b.long_term_debt, b.short_term_debt
        FROM annual_income_statement i
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
        "revenue",
        "operating_income",
        "net_income",
        "interest_expense",
        "stockholders_equity",
        "total_assets",
        "long_term_debt",
        "short_term_debt",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in cols:
        if c not in ("symbol", "fiscal_year"):
            df[c] = df[c].astype(float)
    return df


def build_quality_panel(fund: pd.DataFrame) -> pd.DataFrame:
    out = fund[["symbol", "fiscal_year"]].copy()

    out["roe"] = np.where(fund["stockholders_equity"] > 0, fund["net_income"] / fund["stockholders_equity"], np.nan)
    out["roa"] = np.where(fund["total_assets"] > 0, fund["net_income"] / fund["total_assets"], np.nan)
    out["operating_margin"] = np.where(fund["revenue"] > 0, fund["operating_income"] / fund["revenue"], np.nan)
    out["net_margin"] = np.where(fund["revenue"] > 0, fund["net_income"] / fund["revenue"], np.nan)
    total_debt = fund["long_term_debt"].fillna(0) + fund["short_term_debt"].fillna(0)
    out["debt_to_assets"] = np.where(fund["total_assets"] > 0, total_debt / fund["total_assets"], np.nan)
    out["interest_coverage"] = np.where(
        fund["interest_expense"] > 0, fund["operating_income"] / fund["interest_expense"], np.nan
    )

    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def run(start_date: str, end_date: str, min_cross_section: int, horizon_months: int = 1) -> None:
    logger.info("Fetching annual quality fundamentals (point-in-time reconstruction)")
    fund = fetch_annual_quality_fundamentals()
    logger.info(f"{len(fund)} symbol-fiscal-year rows")
    quality_panel = build_quality_panel(fund)

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly_quality = merge_asof_monthly(months, quality_panel, cols=QUALITY_FACTOR_COLS)

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - horizon_months):
        month = months[i]
        qframe = monthly_quality.get(month)
        if qframe is None or qframe.empty:
            continue
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = qframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        for col in QUALITY_FACTOR_COLS:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Multivariate Fama-MacBeth (all quality-score components jointly) ===")
    print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, QUALITY_FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:18s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each component alone) ===")
    print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in QUALITY_FACTOR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:18s} {mean:10.5f} {t:8.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--horizon-months", type=int, default=1)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.horizon_months)


if __name__ == "__main__":
    main()
