#!/usr/bin/env python3
"""
Fama-MacBeth test of 4 Size-family candidates never tested as standalone factors in this repo:
Enterprise Value, Float-Adjusted Market Cap, Total Assets, Revenue.

ANALYTICAL-COMPLETENESS TASK, NOT A LIVE-SCORING PROPOSAL. Plain market-cap Size was already
extensively tested (t=7.33-8.86 in various composite-level tests, the single strongest factor
ever found in this system) and DELIBERATELY REJECTED as a live-scoring input by explicit user
directive (MEMORY.md size_pillar_removed_entirely_20260826 - "not sure why market cap still
lingering on our scores page we dont want it included there"). That rejection is NOT reconsidered
here. This script exists only because excluding these 4 related-but-distinct candidates from a
from-scratch data-driven analysis (clustering/joint-importance, checking whether the pillar
taxonomy matches what the data shows) just because plain market cap was rejected for LIVE
SCORING would itself be a bias - the analysis should see the data even if the live-scoring
decision on Size stays closed.

Reuses fama_macbeth_value_factors.py's exact conventions: point-in-time per-share/per-firm
fundamentals from annual_income_statement/annual_balance_sheet, 90-day reporting-lag
point-in-time approximation, monthly merge-asof onto month-end prices, z-score+winsorize+
zero-impute panel construction, half-split at the sample midpoint.
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

CANDIDATE_COLS = ["ev", "total_assets_log", "revenue_log"]
# float_adjusted_market_cap NOT included - see FLOAT ADJUSTMENT note in run(): genuinely
# unbuildable, not approximated. insider_ownership_pct was dropped from the schema entirely
# 2026-08-24 ("not a positioning metric") and no other float/free-float-percentage or
# institutional-lockup data source exists anywhere in this pipeline (grep-confirmed against
# loaders/ and migrations/).


def fetch_fundamentals() -> pd.DataFrame:
    sql = """
        SELECT i.symbol, i.fiscal_year, i.revenue,
               i.shares_outstanding_diluted,
               b.total_assets, b.long_term_debt, b.short_term_debt, b.cash_and_equivalents
        FROM annual_income_statement i
        LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
        WHERE i.fiscal_year BETWEEN 2000 AND 2026
          AND COALESCE(i.data_unavailable, false) = false
          AND i.shares_outstanding_diluted > 0
        ORDER BY i.symbol, i.fiscal_year
    """
    with DatabaseContext("read") as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    cols = [
        "symbol",
        "fiscal_year",
        "revenue",
        "shares_diluted",
        "total_assets",
        "long_term_debt",
        "short_term_debt",
        "cash_and_equivalents",
    ]
    df = pd.DataFrame(rows, columns=cols)
    for c in cols:
        if c not in ("symbol", "fiscal_year"):
            df[c] = df[c].astype(float)
    return df


def build_panel(fund: pd.DataFrame) -> pd.DataFrame:
    net_debt = (
        fund["long_term_debt"].fillna(0) + fund["short_term_debt"].fillna(0) - fund["cash_and_equivalents"].fillna(0)
    )
    out = fund[["symbol", "fiscal_year"]].copy()
    out["shares_diluted"] = fund["shares_diluted"]
    out["net_debt"] = net_debt
    out["total_assets"] = fund["total_assets"]
    out["revenue"] = fund["revenue"]
    out["known_date"] = pd.to_datetime(fund["fiscal_year"].astype(str) + "-12-31") + pd.Timedelta(
        days=REPORTING_LAG_DAYS
    )
    return out.dropna(subset=["known_date"])


def compute_candidates(gframe: pd.DataFrame, price: pd.Series) -> pd.DataFrame:
    df = gframe.join(price.rename("price"), how="inner")
    df = df[df["price"] > 0]

    market_cap = df["price"] * df["shares_diluted"]
    out = pd.DataFrame(index=df.index)
    out["size"] = np.where((market_cap >= 1e6) & (market_cap <= 1e13), np.log10(market_cap), np.nan)

    enterprise_value = market_cap + df["net_debt"]
    # EV can be negative (net cash exceeding market cap, e.g. some biotech/holding-co shells) -
    # a real, if unusual, case, not an error. log10 requires positive input, so those rows
    # correctly get NaN here (can't meaningfully log-scale a negative EV) rather than a crash
    # or a sign-flip that would misrepresent them as small-EV.
    out["ev"] = np.where((enterprise_value >= 1e6) & (enterprise_value <= 1e13), np.log10(enterprise_value), np.nan)

    out["total_assets_log"] = np.where(
        (df["total_assets"] >= 1e5) & (df["total_assets"] <= 1e13), np.log10(df["total_assets"]), np.nan
    )
    out["revenue_log"] = np.where((df["revenue"] > 0) & (df["revenue"] <= 1e13), np.log10(df["revenue"]), np.nan)
    return out


def run(start_date: str, end_date: str, min_cross_section: int, horizon_months: int = 1) -> None:
    logger.info("Fetching fundamentals for Size-family candidates")
    fund = fetch_fundamentals()
    panel = build_panel(fund)

    logger.info(f"Pulling month-end price panel {start_date}..{end_date}")
    price_df = fetch_month_end_prices(start_date, end_date)
    px = price_df.pivot(index="month", columns="symbol", values="px").sort_index()
    months = px.index

    monthly_fund = merge_asof_monthly(months, panel, cols=["shares_diluted", "net_debt", "total_assets", "revenue"])

    all_cols = ["size", *CANDIDATE_COLS]
    records: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    for i in range(len(months) - horizon_months):
        month = months[i]
        gframe = monthly_fund.get(month)
        if gframe is None or gframe.empty:
            continue
        cand = compute_candidates(gframe, px.iloc[i])
        fwd_ret = px.iloc[i + horizon_months] / px.iloc[i] - 1.0
        frame = cand.join(fwd_ret.rename("fwd_ret"), how="inner")
        frame = frame.replace([np.inf, -np.inf], np.nan)
        frame = frame.dropna(subset=["fwd_ret"])
        frame = frame[(frame["fwd_ret"] > -0.95) & (frame["fwd_ret"] < 5.0)]
        if len(frame) < min_cross_section:
            continue
        for col in all_cols:
            lo, hi = frame[col].quantile([0.01, 0.99])
            frame[col] = frame[col].clip(lo, hi)
            std = frame[col].std()
            frame[col] = (frame[col] - frame[col].mean()) / std if std and std > 0 else frame[col] * 0.0
        frame[all_cols] = frame[all_cols].fillna(0.0)
        records.append((month, frame))

    if not records:
        raise RuntimeError("No usable cross-sectional months")

    sizes = [len(f) for _, f in records]
    print(f"Usable cross-sectional months: {len(records)}  ({records[0][0]} to {records[-1][0]})")
    print(f"Median cross-section size: {int(np.median(sizes))}\n")

    split_idx = len(records) // 2
    halves = {
        "FULL": records,
        "FIRST_HALF": records[:split_idx],
        "SECOND_HALF": records[split_idx:],
    }

    print("=== Univariate (each candidate alone) ===")
    for label, half in halves.items():
        print(f"\n-- {label} ({half[0][0]} to {half[-1][0]}, n={len(half)}) --")
        print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s}")
        for c in CANDIDATE_COLS:
            uni = _fama_macbeth(half, [c])
            mean, t = uni[c]
            print(f"{c:18s} {mean:10.5f} {t:8.2f}")

    print("\n=== Multivariate, controlling for log(market_cap) ('size') ===")
    for label, half in halves.items():
        print(f"\n-- {label} ({half[0][0]} to {half[-1][0]}, n={len(half)}) --")
        print(f"{'factor':18s} {'mean_coef':>10s} {'t_stat':>8s}")
        multi = _fama_macbeth(half, all_cols)
        for name, (mean, t) in multi.items():
            print(f"{name:18s} {mean:10.5f} {t:8.2f}")

    print(
        "\nFLOAT-ADJUSTED MARKET CAP: NOT TESTED - genuinely unbuildable. insider_ownership_pct "
        "was dropped from the schema entirely 2026-08-24 ('not a positioning metric', see "
        "MEMORY.md) and no other float-percentage, freely-tradeable-shares, or institutional-"
        "lockup data source exists anywhere in this pipeline (grep-confirmed against loaders/ "
        "and migrations/). shares_outstanding_diluted/shares_outstanding_basic are total share "
        "counts, not float - using either as a float proxy would silently misrepresent the "
        "metric rather than honestly report the gap, same discipline as this repo's prior "
        "cash_conversion_cycle finding (accounts_payable also absent, not approximated)."
    )


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
