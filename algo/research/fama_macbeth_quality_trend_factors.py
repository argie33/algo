#!/usr/bin/env python3
"""
Fama-MacBeth test of Quality-trend candidates: margin/ROE trend, earnings-growth stability,
and FCF/NI vs OCF/NI cash-conversion signals.

Built 2026-08-25 (goal: resolve, not just flag, the margin/ROE-trend/eps_growth_stability
placement question raised by the user). Literature check (checked, not assumed): both
Piotroski's F-Score (2000, Journal of Accounting Research - one of the most cited quality/value
papers; uses delta-ROA and delta-gross-margin as 2 of its 9 checks) and Asness/Frazzini/
Pedersen's "Quality Minus Junk" (2019, Review of Accounting Studies - AQR's flagship quality
framework; treats "growth of profitability" as one of quality's four core pillars) place
trend/improvement-in-profitability signals INSIDE quality, not growth and not a separate
bucket. This script tests whether that conceptual placement also holds up empirically in this
dataset's point-in-time panel (same annual-statement reconstruction, same calendar-FYE +
90-day-lag caveat as the other fama_macbeth_*.py scripts).

Field definitions:
- margin_trend = this-year operating_margin minus prior-year operating_margin (percentage
  points), matching this repo's existing gross_margin_trend/operating_margin_trend convention
  (percentage-point delta, not a growth rate).
- roe_trend = this-year ROE minus prior-year ROE (percentage points).
- eps_growth_stability_proxy = stddev of trailing 3 YEARS of annual EPS growth rates (a
  lower-frequency proxy for the live field's real definition - stddev of trailing 4 QUARTERS
  of EPS growth - since this script only has annual-statement data; lower = more consistent).
- fcf_to_ni = free_cash_flow / net_income; ocf_to_ni = operating_cash_flow / net_income (only
  computed when net_income > 0 - a cash-conversion ratio off negative/zero earnings isn't
  meaningful).

Usage:
    python -m algo.research.fama_macbeth_quality_trend_factors [options]
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

TREND_FACTOR_COLS = ["margin_trend", "roe_trend", "eps_growth_stability_proxy", "fcf_to_ni", "ocf_to_ni"]


def fetch_annual_trend_fundamentals() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year,
               i.revenue, i.operating_income, i.net_income, COALESCE(i.diluted_eps, i.eps) AS eps,
               b.stockholders_equity,
               c.free_cash_flow, c.operating_cash_flow
        FROM annual_income_statement i
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
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
        "eps",
        "stockholders_equity",
        "free_cash_flow",
        "operating_cash_flow",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in cols:
        if c not in ("symbol", "fiscal_year"):
            df[c] = df[c].astype(float)
    return df


def build_trend_panel(fund: pd.DataFrame) -> pd.DataFrame:
    fund = fund.sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)
    g = fund.groupby("symbol", group_keys=False)

    operating_margin = np.where(fund["revenue"] > 0, fund["operating_income"] / fund["revenue"], np.nan)
    roe = np.where(fund["stockholders_equity"] > 0, fund["net_income"] / fund["stockholders_equity"], np.nan)
    om_series = pd.Series(operating_margin, index=fund.index)
    roe_series = pd.Series(roe, index=fund.index)

    out = fund[["symbol", "fiscal_year"]].copy()
    out["margin_trend"] = (om_series - om_series.groupby(fund["symbol"]).shift(1)) * 100
    out["roe_trend"] = (roe_series - roe_series.groupby(fund["symbol"]).shift(1)) * 100

    eps_growth = np.where(g["eps"].shift(1) > 0, fund["eps"] / g["eps"].shift(1) - 1.0, np.nan)
    eps_growth_series = pd.Series(eps_growth, index=fund.index)
    out["eps_growth_stability_proxy"] = eps_growth_series.groupby(fund["symbol"]).transform(
        lambda s: s.rolling(3).std()
    )

    out["fcf_to_ni"] = np.where(fund["net_income"] > 0, fund["free_cash_flow"] / fund["net_income"], np.nan)
    out["ocf_to_ni"] = np.where(fund["net_income"] > 0, fund["operating_cash_flow"] / fund["net_income"], np.nan)

    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def run(start_date: str, end_date: str, min_cross_section: int, horizon_months: int = 1) -> None:
    logger.info("Fetching annual trend fundamentals (point-in-time reconstruction)")
    fund = fetch_annual_trend_fundamentals()
    logger.info(f"{len(fund)} symbol-fiscal-year rows")
    trend_panel = build_trend_panel(fund)

    # Report raw correlation between fcf_to_ni and ocf_to_ni before any FM test.
    raw_corr = trend_panel[["fcf_to_ni", "ocf_to_ni"]].dropna().corr().iloc[0, 1]
    print(
        f"Raw fcf_to_ni vs ocf_to_ni correlation (all symbol-years, n={trend_panel[['fcf_to_ni', 'ocf_to_ni']].dropna().shape[0]}): {raw_corr:.3f}\n"
    )

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly_trend = merge_asof_monthly(months, trend_panel, cols=TREND_FACTOR_COLS)

    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - horizon_months):
        month = months[i]
        tframe = monthly_trend.get(month)
        if tframe is None or tframe.empty:
            continue
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = tframe.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        for col in TREND_FACTOR_COLS:
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

    print("=== Multivariate Fama-MacBeth (trend/stability/cash-conversion signals jointly) ===")
    print(f"{'factor':28s} {'mean_coef':>10s} {'t_stat':>8s} {'n_months':>9s}")
    multi = _fama_macbeth(records, TREND_FACTOR_COLS)
    for name, (mean, t) in multi.items():
        print(f"{name:28s} {mean:10.5f} {t:8.2f} {len(records):9d}")

    print("\n=== Univariate Fama-MacBeth (each factor alone) ===")
    print(f"{'factor':28s} {'mean_coef':>10s} {'t_stat':>8s}")
    for c in TREND_FACTOR_COLS:
        uni = _fama_macbeth(records, [c])
        mean, t = uni[c]
        print(f"{c:28s} {mean:10.5f} {t:8.2f}")


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
