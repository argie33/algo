#!/usr/bin/env python3
"""
Fama-MacBeth cross-sectional regression harness for fundamental growth factors.

Built 2026-08-25 (goal: re-audit the inputs cut from stock_scores' Growth pillar in commit
92cd092ce - EPS/Revenue 3y/5y CAGR, NI/OI/FCF/OCF growth YoY - using real point-in-time
evidence instead of the pooled-panel composite backtests that originally justified dropping
them). See algo/research/fama_macbeth_price_factors.py's module docstring for why pooled-panel
significance tests (used throughout this repo's 2026-08-25 factor audits) overstate
significance relative to a proper Fama-MacBeth test.

growth_metrics/quality_metrics/etc. are single-row-per-symbol SNAPSHOTS (no history - see
[[fama_macbeth_price_factor_pipeline_built_20260825]]), so this script does NOT read them.
It reconstructs a point-in-time annual fundamentals panel directly from
annual_income_statement/annual_balance_sheet/annual_cash_flow, then merges it onto the monthly
price grid using an as-of-date join.

POINT-IN-TIME CAVEAT (real limitation, not swept under the rug): none of the three annual
statement tables carry a filing_date or fiscal-year-end date - only an integer `fiscal_year`.
This script assumes every fiscal year ends 2026-12-31 style (calendar year-end) and applies a
flat 90-day reporting lag (a standard 10-K deadline approximation), i.e. fiscal_year Y's
fundamentals are treated as "known" starting April 1 of year Y+1. Real fiscal-year-end dates
(a meaningful minority of the universe reports on a non-calendar fiscal year) would shift this
per-symbol; until fiscal_year_end dates are available, this is a reasonable approximation, not
an exact one - a genuine lookahead-bias risk for non-calendar-FY symbols, flagged here.

Growth-rate convention: YoY/CAGR only computed when both endpoints are positive
(curr/prior - 1, or (curr/prior)**(1/n) - 1 for n-year CAGR) - a growth rate off a
negative/zero base is not well-defined, so those are left NaN rather than guessed.

Usage:
    python -m algo.research.fama_macbeth_growth_factors [options]
    (same --start-date/--end-date/--min-cross-section args as fama_macbeth_price_factors)
"""

import argparse
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from algo.research.fama_macbeth_price_factors import _fama_macbeth, fetch_month_end_prices
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

GROWTH_FACTOR_COLS = [
    "eps_growth_1y",
    "eps_growth_3y",
    "eps_growth_5y",
    "revenue_growth_1y",
    "revenue_growth_3y",
    "revenue_growth_5y",
    "ni_growth_yoy",
    "oi_growth_yoy",
    "fcf_growth_yoy",
    "ocf_growth_yoy",
    "asset_growth_yoy_flipped",
]

REPORTING_LAG_DAYS = 90


def fetch_annual_fundamentals() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year,
               i.revenue, COALESCE(i.diluted_eps, i.eps) AS eps,
               i.net_income, i.operating_income,
               c.free_cash_flow, c.operating_cash_flow,
               b.total_assets
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
    df = pd.DataFrame(
        rows,
        columns=[
            "symbol",
            "fiscal_year",
            "revenue",
            "eps",
            "net_income",
            "operating_income",
            "fcf",
            "ocf",
            "total_assets",
        ],
    )
    for col in ["revenue", "eps", "net_income", "operating_income", "fcf", "ocf", "total_assets"]:
        df[col] = df[col].astype(float)
    return df


def _growth_rate(curr: pd.Series, prior: pd.Series, n_years: int = 1) -> pd.Series:
    """(curr/prior)**(1/n) - 1, only where both endpoints are positive."""
    valid = (prior > 0) & (curr > 0)
    out = pd.Series(np.nan, index=curr.index)
    out[valid] = (curr[valid] / prior[valid]) ** (1.0 / n_years) - 1.0
    return out


def build_growth_panel(fund: pd.DataFrame) -> pd.DataFrame:
    fund = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    g = fund.groupby("symbol", group_keys=False)

    def _shifted(col: str, periods: int) -> pd.Series:
        return g[col].shift(periods)

    out = fund[["symbol", "fiscal_year"]].copy()
    out["eps_growth_1y"] = _growth_rate(fund["eps"], _shifted("eps", 1), 1)
    out["eps_growth_3y"] = _growth_rate(fund["eps"], _shifted("eps", 3), 3)
    out["eps_growth_5y"] = _growth_rate(fund["eps"], _shifted("eps", 5), 5)
    out["revenue_growth_1y"] = _growth_rate(fund["revenue"], _shifted("revenue", 1), 1)
    out["revenue_growth_3y"] = _growth_rate(fund["revenue"], _shifted("revenue", 3), 3)
    out["revenue_growth_5y"] = _growth_rate(fund["revenue"], _shifted("revenue", 5), 5)
    out["ni_growth_yoy"] = _growth_rate(fund["net_income"], _shifted("net_income", 1), 1)
    out["oi_growth_yoy"] = _growth_rate(fund["operating_income"], _shifted("operating_income", 1), 1)
    out["fcf_growth_yoy"] = _growth_rate(fund["fcf"], _shifted("fcf", 1), 1)
    out["ocf_growth_yoy"] = _growth_rate(fund["ocf"], _shifted("ocf", 1), 1)
    asset_growth_yoy = _growth_rate(fund["total_assets"], _shifted("total_assets", 1), 1)
    # Sign-flipped to match stock_scores' kept convention (low asset growth = good), so a
    # positive multivariate coefficient here is directly comparable to the other factors.
    out["asset_growth_yoy_flipped"] = -asset_growth_yoy

    # "Known as of" date: calendar fiscal year-end (Dec 31) + a flat 90-day reporting lag
    # (lands ~end of March / start of April the following year). See module docstring
    # point-in-time caveat.
    out["known_date"] = pd.to_datetime(out["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def merge_asof_monthly(
    px_months: pd.DatetimeIndex, panel: pd.DataFrame, cols: list[str] | None = None
) -> dict[pd.Timestamp, pd.DataFrame]:
    """For each month-end, return each symbol's most-recently-known fundamentals row (as-of
    join). Generic over any panel with a `known_date` column - reused by
    fama_macbeth_value_factors.py for a different column set."""
    cols = cols if cols is not None else GROWTH_FACTOR_COLS
    panel = panel.sort_values(["symbol", "known_date"])
    result: dict[pd.Timestamp, pd.DataFrame] = {}
    for month in px_months:
        cutoff = pd.Timestamp(month) + pd.offsets.MonthEnd(0)
        eligible = panel[panel["known_date"] <= cutoff]
        latest = eligible.sort_values("known_date").groupby("symbol", as_index=False).last()
        result[month] = latest.set_index("symbol")[cols]
    return result


def run(start_date: str, end_date: str, min_cross_section: int, horizon_months: int = 1) -> None:
    logger.info("Fetching annual fundamentals (point-in-time reconstruction)")
    fund = fetch_annual_fundamentals()
    logger.info(f"{len(fund)} symbol-fiscal-year rows")
    growth_panel = build_growth_panel(fund)

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    ret = px.pct_change(fill_method=None)
    months = ret.index

    monthly_growth = merge_asof_monthly(months, growth_panel)

    if horizon_months > 1:
        print(
            f"NOTE: horizon={horizon_months} months uses OVERLAPPING windows (consecutive "
            f"months share {horizon_months - 1} months of return) - induces serial correlation "
            f"in the FM coefficient series beyond what the plain t-stat formula assumes, so "
            f"these t-stats are optimistic/inflated versus the 1-month case. Directional "
            f"comparison to the 1-month result is still informative; treat the magnitude with "
            f"more skepticism.\n"
        )

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - horizon_months):
        month = months[i]
        gframe = monthly_growth.get(month)
        if gframe is None or gframe.empty:
            continue
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = gframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        for col in GROWTH_FACTOR_COLS:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std > 0 else 0.0
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months - check fundamentals coverage / date range")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    print("=== Multivariate Fama-MacBeth (all growth factors jointly, controls for each other) ===")
    print(f"{'factor':26s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, GROWTH_FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:26s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each growth factor alone) ===")
    print(f"{'factor':26s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in GROWTH_FACTOR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:26s} {mean:10.5f} {t:8.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start-date", default="2014-01-01")
    parser.add_argument("--end-date", default=datetime.now(tz=None).date().isoformat())
    parser.add_argument("--min-cross-section", type=int, default=100)
    parser.add_argument("--horizon-months", type=int, default=1, help="Forward return horizon in months (default 1)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.start_date, args.end_date, args.min_cross_section, args.horizon_months)


if __name__ == "__main__":
    main()
